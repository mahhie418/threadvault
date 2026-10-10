"""Messages that a backup fetches from Slack."""

import collections.abc
import datetime
import decimal
import typing

def window(
    now: datetime.datetime,
    days: int | None
) -> tuple[str, str]:

    """Gives the timestamps of the oldest and the latest message to fetch.

    Args:
        now: The current time, which ends the window.
        days: Number of days before `now` that the window covers,
              or None for every message.

    Returns:
        The two timestamps, written as Slack writes the timestamps of
        messages. A window of every message starts at 0, as Slack refuses
        0.000000.
    """

    oldest = '0' if days is None else f'{(now - datetime.timedelta(days = days)).timestamp():.6f}'

    return oldest, f'{now.timestamp():.6f}'

def threads(
    history: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    stored: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    marked: collections.abc.Iterable[str] = ()
) -> list[str]:

    """Picks the threads to fetch, among the parents in the history and the marked threads.

    A thread is fetched when the number of its replies or the timestamp of
    its latest reply differs from the parent that the vault holds, as after a
    new thread or a new reply. A reply that was only edited changes neither,
    so its thread is not fetched. A marked thread is fetched whatever its
    parent, as its parent may be older than the history.

    Args:
        history: Messages that conversations.history returned.
        stored: Messages that the vault holds for the channel.
        marked: Timestamps of the parent messages of the threads that events marked.

    Returns:
        Timestamps of the parent messages, in order of time.
    """

    parents = {message['ts']: message for message in stored}

    return sorted({*(message['ts'] for message in history if _summarise(message) != _summarise(parents.get(message['ts'], {}))), *marked}, key = decimal.Decimal)

def _summarise(
    message: collections.abc.Mapping[str, typing.Any]
) -> tuple[int, str | None]:

    return message.get('reply_count', 0), message.get('latest_reply')
