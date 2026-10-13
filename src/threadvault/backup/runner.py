"""One run that backs up the workspace into a vault directory, or into its vault on GitHub."""

import collections.abc
import contextlib
import dataclasses
import datetime
import itertools
import json
import logging
import os
import pathlib
import sqlite3
import typing

import slack_sdk
import slack_sdk.errors

import threadvault.backup.backlog
import threadvault.backup.fetch
import threadvault.configuration
import threadvault.customisation
import threadvault.github.rest
import threadvault.product
import threadvault.slack.api
import threadvault.vault.export
import threadvault.vault.files
import threadvault.vault.layout
import threadvault.vault.markdown
import threadvault.vault.merge
import threadvault.vault.repository
import threadvault.vault.state

ATTRIBUTES_FILE = '.gitattributes'
_ATTRIBUTES_CONTENT = '*.json text eol=lf\n*.md text eol=lf\n'
VAULTS_DIRECTORY = 'vaults'

_LOGGER = logging.getLogger(__name__)

class LockError(Exception):

    """Raised when another backup is already writing the clone of the vault."""

class VaultError(Exception):

    """Raised when the repository of the vault must not receive the backup, because it is public or gone."""

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
        files: Number of attached files that the run saved.
        failures: Number of attached files that the run could not save.
    """

    channel: str
    directory: str
    messages: int
    deleted: int
    withheld: int
    files: int
    failures: int

def run(
    client: slack_sdk.web.WebClient,
    vault: pathlib.Path,
    settings: threadvault.customisation.Settings,
    *,
    days: int | None,
    limit: int | None,
    now: datetime.datetime,
    checkpoint: collections.abc.Callable[[Result], None] | None = None,
    backlog: threadvault.backup.backlog.Backlog | None = None
) -> list[Result]:

    """Backs up the workspace into a vault directory.

    The run backs up the channels that the bot is a member of, only the
    selected ones in 'selected' mode. A channel that the vault does not hold
    yet, and every channel when `days` is None, is fetched in full, and
    nothing is deleted from it. Any other channel is fetched for the last
    `days` days and merged into what the vault holds.
    A renamed channel first moves to the directory of its new name. The vault
    then gets the users and the channels, the messages of each channel as
    Slack's export writes them, the Markdown of each channel and its index,
    and the state file. When the settings enable attachments, the attached
    files of the messages that the run fetched are saved too, up to the size
    limit of the settings; a file that cannot be saved is tried again when
    its message is fetched again. A channel fetched in full joins the state
    file as soon as it is written, so that a run that stops part way does not
    fetch it in full again.

    When the settings let the bot join channels, it first joins the public
    channels that it is not in, except archived ones: every one in 'joined'
    mode, and the selected ones in 'selected' mode. A channel that it cannot
    join is left out, with a warning.

    The threads that events marked are fetched again whatever their age, as
    a reply to a thread older than `days` changes no message in the history.
    So is each marked day older than `days`, as an edit or a deletion there
    is not in the history either.

    Args:
        client: Slack client for the workspace.
        vault: Root directory of the vault, created when missing.
        settings: Settings of the workspace.
        days: Number of recent days to fetch again, or None to fetch every channel in full.
        limit: Most messages that the run may delete, or None for no limit.
        now: The current time.
        checkpoint: Function called with the result of each channel fetched in full,
                    once the state file lists it, or None.
        backlog: What events marked for the run to fetch again, or None.

    Returns:
        What the run did to each channel, in the order of conversations.list.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
        threadvault.vault.state.StateError: The state file of the vault cannot be used.
    """

    url = client.auth_test().get('url', '')
    users = threadvault.slack.api.users(client)
    channels = threadvault.slack.api.channels(client)
    joined = _join(client, channels, settings)
    targets = [channel for channel in channels if (channel.get('is_member') or channel['id'] in joined) and (settings.channel_mode == 'joined' or channel['id'] in settings.channels_selected)]
    members = {channel['id']: threadvault.slack.api.members(client, channel['id']) for channel in targets}
    previous = threadvault.vault.state.load(vault)
    directories = threadvault.vault.layout.assign({channel['id']: channel['name'] for channel in targets}, previous)
    raw = pathlib.Path(os.path.join(vault, threadvault.vault.export.RAW_DIRECTORY))
    transcripts = pathlib.Path(os.path.join(vault, threadvault.vault.markdown.TRANSCRIPTS_DIRECTORY))
    progress = {channel: directory for channel, directory in directories.items() if channel in previous}
    marked = backlog or threadvault.backup.backlog.Backlog()
    results = []

    _move((raw, transcripts), previous, directories)

    raw.mkdir(parents = True, exist_ok = True)
    threadvault.vault.export.users(raw, users)
    threadvault.vault.export.channels(raw, targets, members)

    for channel in targets:

        recent = days is not None and channel['id'] in previous
        directory = directories[channel['id']]
        stored = _read(pathlib.Path(os.path.join(raw, directory)))
        oldest, latest = threadvault.backup.fetch.window(now, days if recent else None)
        windows = [(oldest, latest), *threadvault.backup.fetch.days(marked.days.get(channel['id'], ()), oldest)]
        history = [message for start, end in windows for message in threadvault.slack.api.history(client, channel['id'], oldest = start, latest = end)]
        threads = {thread_ts: threadvault.slack.api.replies(client, channel['id'], thread_ts) for thread_ts in threadvault.backup.fetch.threads(history, stored, marked.threads.get(channel['id'], ()))}
        outcome = threadvault.vault.merge.merge(stored, history, threads, windows = windows, now = now, limit = limit if recent else 0)
        saved, failed = _download(client, vault, itertools.chain(history, *threads.values()), settings.attachment_size_maximum * 1024 * 1024) if settings.attachments_enabled else (0, 0)
        paths = {file['id']: threadvault.vault.files.locate(file) for file in threadvault.vault.files.select(outcome.messages)}
        attachments = {file_id: path for file_id, path in paths.items() if pathlib.Path(os.path.join(vault, path)).is_file()}

        threadvault.vault.export.messages(pathlib.Path(os.path.join(raw, directory)), outcome.messages, users)
        threadvault.vault.markdown.transcribe(pathlib.Path(os.path.join(transcripts, directory)), channel, outcome.messages, users = users, channels = channels, attachments = attachments, url = url, timezone = settings.workspace_timezone, language = settings.markdown_language)

        if limit is not None: limit -= len(outcome.deleted)

        results.append(Result(channel = channel['id'], directory = directory, messages = len(outcome.messages), deleted = len(outcome.deleted), withheld = len(outcome.withheld), files = saved, failures = failed))

        if recent: continue

        progress[channel['id']] = directory
        threadvault.vault.state.save(vault, progress)

        if checkpoint is not None: checkpoint(results[-1])

    threadvault.vault.markdown.catalogue(vault, targets, directories, timezone = settings.workspace_timezone, language = settings.markdown_language)
    threadvault.vault.state.save(vault, directories)

    return results

def publish(
    client: slack_sdk.web.WebClient,
    settings: threadvault.customisation.Settings,
    *,
    directory: pathlib.Path,
    full_name: str,
    token: collections.abc.Callable[[], str],
    days: int | None,
    limit: int | None,
    now: datetime.datetime,
    backlog: threadvault.backup.backlog.Backlog | None = None
) -> tuple[list[Result], str]:

    """Backs up the workspace into its vault on GitHub.

    First, git must be new enough, as an older one would ignore the settings
    that keep it apart from the machine. The repository is created as
    private when it does not exist, and refused when it is public. The vault
    is cloned into `directory`, or made to match GitHub there, and gets a
    README and .gitattributes when it has none; then `run` backs up the
    workspace into it. Each channel fetched in full is committed and pushed
    on its own, so that a long first run keeps its progress, and the rest
    goes into one commit at the end. Before every push, the repository must
    still be private.

    The backup holds the lock of the clone throughout, as `hold` does, so
    that no other backup writes the clone meanwhile.

    Args:
        client: Slack client for the workspace.
        settings: Settings of the workspace.
        directory: Directory for the clone of the vault.
        full_name: Repository of the vault, as owner/name.
        token: Function that gives a current GitHub access token.
        days: Number of recent days to fetch again, or None to fetch every channel in full.
        limit: Most messages that the run may delete, or None for no limit.
        now: The current time.
        backlog: What events marked for the run to fetch again, or None.

    Returns:
        What the run did to each channel, in the order of conversations.list,
        and the full ID of the commit that the vault is at after the backup.

    Raises:
        LockError: Another backup is already writing the clone.
        VaultError: The repository is public, or has disappeared.
        threadvault.github.rest.GitHubError: GitHub refused a request, or could not be reached.
        threadvault.vault.repository.GitError: git is missing or too old, or a git command failed.
        slack_sdk.errors.SlackApiError: Slack refused a request.
        threadvault.vault.state.StateError: The state file of the vault cannot be used.
    """

    with hold(directory):

        threadvault.vault.repository.verify()

        found = threadvault.github.rest.repository(token(), full_name) or threadvault.github.rest.create(token(), full_name)

        if not found['private']: raise VaultError(f'{full_name} is public; {threadvault.product.NAME} backs up only into private repositories')

        user = threadvault.github.rest.user(token())
        repository = threadvault.vault.repository.Repository(directory, token = token, name = user['login'], email = f'{user['id']}+{user['login']}@users.noreply.github.com')

        if pathlib.Path(os.path.join(directory, '.git')).is_dir(): repository.refresh()
        else: repository.clone(found['clone_url'])

        _prepare(directory, full_name.partition('/')[2], settings.markdown_language)

        def checkpoint(
            result: Result
        ) -> None:

            _push(repository, f'Back up #{result.directory}', token, full_name)

        results = run(client, directory, settings, days = days, limit = limit, now = now, checkpoint = checkpoint, backlog = backlog)

        _push(repository, f'Back up at {now:%Y-%m-%d %H:%M} UTC', token, full_name)

        return results, repository.head()

@contextlib.contextmanager
def hold(
    directory: pathlib.Path
) -> collections.abc.Generator[None]:

    """Holds the lock of the clone of a vault while a backup writes it.

    The lock file sits next to the clone and works as
    `threadvault.slack.application.lock` does.

    Args:
        directory: Directory of the clone; its parent is created when missing.

    Yields:
        Nothing; the lock is held until the block ends.

    Raises:
        LockError: Another backup holds the lock.
    """

    directory.parent.mkdir(parents = True, exist_ok = True)

    connection = sqlite3.connect(pathlib.Path(os.path.join(directory.parent, f'{directory.name}.lock')), timeout = 0, autocommit = True)

    try:

        try: connection.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError: raise LockError(f'Another backup is already writing {directory}') from None

        yield

    finally:

        connection.close()

def _prepare(
    directory: pathlib.Path,
    name: str,
    language: threadvault.configuration.Language
) -> None:

    attributes = pathlib.Path(os.path.join(directory, ATTRIBUTES_FILE))

    if not attributes.exists(): attributes.write_text(_ATTRIBUTES_CONTENT, encoding = 'utf-8', newline = '\n')

    threadvault.vault.markdown.introduce(directory, name, language = language)

def _push(
    repository: threadvault.vault.repository.Repository,
    message: str,
    token: collections.abc.Callable[[], str],
    full_name: str
) -> None:

    if not repository.commit(message): return

    found = threadvault.github.rest.repository(token(), full_name)

    if found is None or not found['private']: raise VaultError(f'{full_name} is no longer a private repository, so the backup was not pushed')

    repository.push()

def _join(
    client: slack_sdk.web.WebClient,
    channels: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    settings: threadvault.customisation.Settings
) -> set[str]:

    joined = set()

    if not settings.channels_joined: return joined

    for channel in channels:

        if channel.get('is_private') or channel.get('is_member') or channel.get('is_archived'): continue
        if settings.channel_mode == 'selected' and channel['id'] not in settings.channels_selected: continue

        try: threadvault.slack.api.join(client, channel['id'])
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Channel %s not joined: %s', channel['id'], error)
        else: joined.add(channel['id'])

    return joined

def _download(
    client: slack_sdk.web.WebClient,
    vault: pathlib.Path,
    messages: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    limit: int
) -> tuple[int, int]:

    saved, failed = 0, 0

    for file in threadvault.vault.files.select(messages):

        path = pathlib.Path(os.path.join(vault, threadvault.vault.files.locate(file)))

        if path.is_file() or file.get('size', 0) > limit: continue

        try: threadvault.slack.api.download(client, file, path, limit = limit)
        except threadvault.slack.api.DownloadError as error: _LOGGER.warning('Attached file not saved: %s', error); failed += 1
        else: saved += 1

    return saved, failed

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
