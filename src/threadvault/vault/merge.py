"""Merging of the messages fetched from Slack into the messages of the vault."""

import collections.abc
import dataclasses
import decimal
import itertools
import typing

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Outcome:

    """Messages of a channel after a merge.

    Attributes:
        messages: Every message that the vault keeps, in order of time.
        deleted: Messages that the vault held but Slack no longer has.
    """

    messages: list[dict[str, typing.Any]]
    deleted: list[dict[str, typing.Any]]

def merge(
    stored: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    history: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    threads: collections.abc.Mapping[str, collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]]],
    *,
    oldest: str,
    latest: str
) -> Outcome:

    """Merges messages fetched from Slack into the messages of a channel.

    Each result from Slack is the whole truth only about what it covers. The
    history covers the messages posted from `oldest` to `latest` that are not
    thread replies; the replies of a thread cover that thread. A stored
    message that a result covers but does not contain was deleted in Slack.
    Every other stored message stays, such as a reply to an older thread that
    was not fetched again. A fetched message replaces the stored message with
    the same timestamp.

    Args:
        stored: Messages that the vault holds for the channel.
        history: Messages that conversations.history returned.
        threads: Messages that conversations.replies returned, by thread timestamp.
        oldest: Timestamp of the oldest message that the history covers.
        latest: Timestamp of the latest message that the history covers.

    Returns:
        The messages after the merge, and the deleted ones.
    """

    fetched = {message['ts']: dict(message) for message in itertools.chain(history, *threads.values())}
    window = (decimal.Decimal(oldest), decimal.Decimal(latest))
    unknown: dict[str, dict[str, typing.Any]] = {}
    deleted: list[dict[str, typing.Any]] = []

    for message in stored:

        if not (covered := _cover(message, threads, window)): unknown[message['ts']] = dict(message)
        if covered and message['ts'] not in fetched: deleted.append(dict(message))

    messages = sorted((unknown | fetched).values(), key = lambda message: decimal.Decimal(message['ts']))

    return Outcome(messages = messages, deleted = sorted(deleted, key = lambda message: decimal.Decimal(message['ts'])))

def _cover(
    message: collections.abc.Mapping[str, typing.Any],
    threads: collections.abc.Mapping[str, object],
    window: tuple[decimal.Decimal, decimal.Decimal]
) -> bool:

    if (thread_ts := message.get('thread_ts', message['ts'])) in threads: return True

    return thread_ts == message['ts'] and window[0] <= decimal.Decimal(message['ts']) <= window[1]
