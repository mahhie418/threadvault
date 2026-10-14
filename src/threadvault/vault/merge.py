# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Merging of the messages fetched from Slack into the messages of the vault."""

import collections.abc
import dataclasses
import datetime
import decimal
import itertools
import typing

DELETION_DAYS_MAXIMUM = 83

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Outcome:

    """Messages of a channel after a merge.

    Attributes:
        messages: Every message that the vault keeps, in order of time.
        deleted: Messages that the vault held but Slack no longer has.
        withheld: Messages that Slack no longer has but the vault keeps,
                  because there were more deletions than allowed.
    """

    messages: list[dict[str, typing.Any]]
    deleted: list[dict[str, typing.Any]]
    withheld: list[dict[str, typing.Any]]

def merge(
    stored: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    history: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    threads: collections.abc.Mapping[str, collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]]],
    *,
    windows: collections.abc.Collection[tuple[str, str]],
    now: datetime.datetime,
    limit: int | None
) -> Outcome:

    """Merges messages fetched from Slack into the messages of a channel.

    Each result from Slack is the whole truth only about what it covers. The
    history covers the messages posted within each of `windows` that are not
    thread replies; the replies of a thread cover that thread. A stored
    message that a result covers but does not contain was deleted in Slack,
    unless it is older than `DELETION_DAYS_MAXIMUM` days. Every other stored
    message stays, such as a reply to an older thread that was not fetched
    again. A fetched message replaces the stored message with the same
    timestamp. When there are more deletions than `limit`, none of them is made.

    Args:
        stored: Messages that the vault holds for the channel.
        history: Messages that conversations.history returned.
        threads: Messages that conversations.replies returned, by thread timestamp.
        windows: Timestamps of the oldest and the latest message of each span of time that the history covers.
        now: The current time, which sets the age of the messages.
        limit: Most deletions to make, or None for no limit.
               0 keeps every message, as the first run needs.

    Returns:
        The messages after the merge, and the deleted and withheld ones.
    """

    fetched = {message['ts']: dict(message) for message in itertools.chain(history, *threads.values())}
    bounds = [(decimal.Decimal(oldest), decimal.Decimal(latest)) for oldest, latest in windows]
    deletable = decimal.Decimal((now - datetime.timedelta(days = DELETION_DAYS_MAXIMUM)).timestamp())
    unknown: dict[str, dict[str, typing.Any]] = {}
    deleted: list[dict[str, typing.Any]] = []

    for message in stored:

        if not (covered := _cover(message, threads, bounds) and decimal.Decimal(message['ts']) >= deletable): unknown[message['ts']] = dict(message)
        if covered and message['ts'] not in fetched: deleted.append(dict(message))

    deleted.sort(key = lambda message: decimal.Decimal(message['ts']))
    withheld = deleted if limit is not None and len(deleted) > limit else []
    messages = sorted((unknown | {message['ts']: message for message in withheld} | fetched).values(), key = lambda message: decimal.Decimal(message['ts']))

    return Outcome(messages = messages, deleted = [] if withheld else deleted, withheld = withheld)

def _cover(
    message: collections.abc.Mapping[str, typing.Any],
    threads: collections.abc.Mapping[str, object],
    bounds: collections.abc.Iterable[tuple[decimal.Decimal, decimal.Decimal]]
) -> bool:

    if (thread_ts := message.get('thread_ts', message['ts'])) in threads: return True

    return thread_ts == message['ts'] and any(oldest <= decimal.Decimal(message['ts']) <= latest for oldest, latest in bounds)
