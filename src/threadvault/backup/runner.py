"""One run that backs up the workspace into a vault directory."""

import collections.abc
import dataclasses
import datetime
import json
import os
import pathlib
import typing

import slack_sdk

import threadvault.backup.fetch
import threadvault.customisation
import threadvault.slack.api
import threadvault.vault.export
import threadvault.vault.layout
import threadvault.vault.markdown
import threadvault.vault.merge
import threadvault.vault.state

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Result:

    """What a run did to one channel.

    Attributes:
        channel: ID of the channel.
        directory: Name of the directory of the channel in the vault.
        messages: Number of messages that the vault keeps for the channel.
        deleted: Number of messages deleted because Slack no longer has them.
        withheld: Number of messages that Slack no longer has but the vault
                  keeps, because the run would have deleted too many.
    """

    channel: str
    directory: str
    messages: int
    deleted: int
    withheld: int

def run(
    client: slack_sdk.web.WebClient,
    vault: pathlib.Path,
    settings: threadvault.customisation.Settings,
    *,
    days: int,
    limit: int | None,
    now: datetime.datetime
) -> list[Result]:

    """Backs up the workspace into a vault directory.

    The run backs up the channels that the bot is a member of, only the
    selected ones in 'selected' mode. A channel that the vault does not hold
    yet is fetched in full, and nothing is deleted from it. Any other channel
    is fetched for the last `days` days and merged into what the vault holds.
    A renamed channel first moves to the directory of its new name. The vault
    then gets the users and the channels, the messages of each channel as
    Slack's export writes them, the Markdown of each channel and its index,
    and the state file.

    Args:
        client: Slack client for the workspace.
        vault: Root directory of the vault, created when missing.
        settings: Settings of the workspace.
        days: Number of recent days to fetch again.
        limit: Most messages that the run may delete, or None for no limit.
        now: The current time.

    Returns:
        What the run did to each channel, in the order of conversations.list.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
        threadvault.vault.state.StateError: The state file of the vault cannot be used.
    """

    url = client.auth_test().get('url', '')
    users = threadvault.slack.api.users(client)
    channels = threadvault.slack.api.channels(client)
    targets = [channel for channel in channels if channel.get('is_member') and (settings.channel_mode == 'joined' or channel['id'] in settings.channels_selected)]
    members = {channel['id']: threadvault.slack.api.members(client, channel['id']) for channel in targets}
    previous = threadvault.vault.state.load(vault)
    directories = threadvault.vault.layout.assign({channel['id']: channel['name'] for channel in targets}, previous)
    raw = pathlib.Path(os.path.join(vault, threadvault.vault.export.RAW_DIRECTORY))
    transcripts = pathlib.Path(os.path.join(vault, threadvault.vault.markdown.TRANSCRIPTS_DIRECTORY))
    results: list[Result] = []

    _move((raw, transcripts), previous, directories)

    raw.mkdir(parents = True, exist_ok = True)
    threadvault.vault.export.users(raw, users)
    threadvault.vault.export.channels(raw, targets, members)

    for channel in targets:

        known = channel['id'] in previous
        directory = directories[channel['id']]
        stored = _read(pathlib.Path(os.path.join(raw, directory)))
        oldest, latest = threadvault.backup.fetch.window(now, days if known else None)
        history = threadvault.slack.api.history(client, channel['id'], oldest = oldest, latest = latest)
        threads = {thread_ts: threadvault.slack.api.replies(client, channel['id'], thread_ts) for thread_ts in threadvault.backup.fetch.threads(history, stored)}
        outcome = threadvault.vault.merge.merge(stored, history, threads, oldest = oldest, latest = latest, now = now, limit = limit if known else 0)

        threadvault.vault.export.messages(pathlib.Path(os.path.join(raw, directory)), outcome.messages, users)
        threadvault.vault.markdown.transcribe(pathlib.Path(os.path.join(transcripts, directory)), channel, outcome.messages, users = users, channels = channels, url = url, timezone = settings.workspace_timezone, language = settings.markdown_language)

        if limit is not None: limit -= len(outcome.deleted)

        results.append(Result(channel = channel['id'], directory = directory, messages = len(outcome.messages), deleted = len(outcome.deleted), withheld = len(outcome.withheld)))

    threadvault.vault.markdown.catalogue(vault, targets, directories, timezone = settings.workspace_timezone, language = settings.markdown_language)
    threadvault.vault.state.save(vault, directories)

    return results

def _move(
    parents: collections.abc.Iterable[pathlib.Path],
    previous: collections.abc.Mapping[str, str],
    directories: collections.abc.Mapping[str, str]
) -> None:

    moves = {channel: (previous[channel], directory) for channel, directory in directories.items() if previous.get(channel, directory) != directory}
    steps = [(old, f'.{channel}') for channel, (old, _) in moves.items()] + [(f'.{channel}', new) for channel, (_, new) in moves.items()]

    for parent in parents:

        for source, target in steps:

            path = pathlib.Path(os.path.join(parent, source))

            if path.exists(): path.rename(pathlib.Path(os.path.join(parent, target)))

def _read(
    directory: pathlib.Path
) -> list[dict[str, typing.Any]]:

    return [message for path in sorted(directory.glob('*.json')) for message in json.loads(path.read_text(encoding = 'utf-8'))]
