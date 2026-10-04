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
        The two timestamps, written as Slack writes the timestamps of messages.
    """

    start = datetime.datetime.fromtimestamp(0, datetime.UTC) if days is None else now - datetime.timedelta(days = days)

    return f'{start.timestamp():.6f}', f'{now.timestamp():.6f}'

def threads(
    history: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    stored: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]]
) -> list[str]:

    """Picks the threads to fetch, among the parents in the history.

    A thread is fetched when the number of its replies or the timestamp of
    its latest reply differs from the parent that the vault holds, as after a
    new thread or a new reply. A reply that was only edited changes neither,
    so its thread is not fetched.

    Args:
        history: Messages that conversations.history returned.
        stored: Messages that the vault holds for the channel.

    Returns:
        Timestamps of the parent messages, in order of time.
    """

    parents = {message['ts']: message for message in stored}

    return sorted((message['ts'] for message in history if _summarise(message) != _summarise(parents.get(message['ts'], {}))), key = decimal.Decimal)

def _summarise(
    message: collections.abc.Mapping[str, typing.Any]
) -> tuple[int, str | None]:

    return message.get('reply_count', 0), message.get('latest_reply')
