"""Threads and days that events in the workspace marked for the next backup to fetch again."""

import collections.abc
import dataclasses
import datetime
import sqlite3

import threadvault.storage

_THREAD_SELECT = 'SELECT channel_id, thread_ts FROM thread WHERE workspace_id = ?'

_THREAD_UPSERT = """
    INSERT INTO thread (workspace_id, channel_id, thread_ts, mark_time)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (workspace_id, channel_id, thread_ts) DO UPDATE SET
        mark_time = excluded.mark_time
"""

_THREAD_DELETE = 'DELETE FROM thread WHERE workspace_id = ? AND mark_time <= ?'

_DAY_SELECT = 'SELECT channel_id, message_date FROM day WHERE workspace_id = ?'

_DAY_UPSERT = """
    INSERT INTO day (workspace_id, channel_id, message_date, mark_time)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (workspace_id, channel_id, message_date) DO UPDATE SET
        mark_time = excluded.mark_time
"""

_DAY_DELETE = 'DELETE FROM day WHERE workspace_id = ? AND mark_time <= ?'

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Backlog:

    """What events marked in one workspace for the next backup to fetch again.

    Attributes:
        threads: Timestamps of the parent messages of the marked threads, by channel ID.
        days: Marked days, in UTC, by channel ID.
    """

    threads: dict[str, frozenset[str]] = dataclasses.field(default_factory = dict[str, frozenset[str]])
    days: dict[str, frozenset[datetime.date]] = dataclasses.field(default_factory = dict[str, frozenset[datetime.date]])

class BacklogIO:

    """Reads and writes what events marked in each workspace for the next backup to fetch again."""

    def __init__(
        self,
        database: threadvault.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the marks.
        """

        self._database = database

    def load(
        self,
        workspace_id: str
    ) -> Backlog:

        """Loads what events marked in a workspace.

        Args:
            workspace_id: Slack workspace ID.

        Returns:
            The marks.
        """

        connection = self._database.connect()

        return Backlog(threads = _group(connection.execute(_THREAD_SELECT, (workspace_id,)).fetchall(), str), days = _group(connection.execute(_DAY_SELECT, (workspace_id,)).fetchall(), datetime.date.fromisoformat))

    def mark(
        self,
        workspace_id: str,
        channel_id: str,
        target: str | datetime.date,
        time: datetime.datetime
    ) -> None:

        """Marks a thread or a day of a channel for the next backup to fetch again.

        A thread or a day marked again keeps one mark, with the later time.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: ID of the channel.
            target: Timestamp of the parent message of the thread, or the day,
                    in UTC, of the edited or deleted message.
            time: When the event came.
        """

        match target:

            case str(): statement, value = _THREAD_UPSERT, target
            case datetime.date(): statement, value = _DAY_UPSERT, target.isoformat()

        with self._database.begin() as connection: connection.execute(statement, (workspace_id, channel_id, value, time.astimezone(datetime.UTC).isoformat()))

    def clear(
        self,
        workspace_id: str,
        time: datetime.datetime
    ) -> None:

        """Removes the marks of a workspace once a backup that loaded them has succeeded.

        A mark made again after `time` stays, as the backup may have fetched
        the thread or the day before the event that marked it again.

        Args:
            workspace_id: Slack workspace ID.
            time: When the backup loaded the marks.
        """

        until = time.astimezone(datetime.UTC).isoformat()

        with self._database.begin() as connection:

            connection.execute(_THREAD_DELETE, (workspace_id, until))
            connection.execute(_DAY_DELETE, (workspace_id, until))

def _group[T](
    rows: collections.abc.Collection[sqlite3.Row],
    convert: collections.abc.Callable[[str], T]
) -> dict[str, frozenset[T]]:

    return {channel: frozenset(convert(value) for key, value in rows if key == channel) for channel in {key for key, _ in rows}}
