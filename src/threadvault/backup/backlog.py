"""Threads that events in the workspace marked for the next backup to fetch again."""

import dataclasses
import datetime

import threadvault.storage

_THREAD_SELECT = 'SELECT channel_id, thread_ts FROM thread WHERE workspace_id = ?'

_THREAD_UPSERT = """
    INSERT INTO thread (workspace_id, channel_id, thread_ts, mark_time)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (workspace_id, channel_id, thread_ts) DO UPDATE SET
        mark_time = excluded.mark_time
"""

_THREAD_DELETE = 'DELETE FROM thread WHERE workspace_id = ? AND mark_time <= ?'

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Backlog:

    """What events marked in one workspace for the next backup to fetch again.

    Attributes:
        threads: Timestamps of the parent messages of the marked threads, by channel ID.
    """

    threads: dict[str, frozenset[str]] = dataclasses.field(default_factory = dict[str, frozenset[str]])

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

        rows = self._database.connect().execute(_THREAD_SELECT, (workspace_id,)).fetchall()

        return Backlog(threads = {channel: frozenset(row['thread_ts'] for row in rows if row['channel_id'] == channel) for channel in {row['channel_id'] for row in rows}})

    def mark(
        self,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
        time: datetime.datetime
    ) -> None:

        """Marks a thread for the next backup to fetch again.

        A thread marked again keeps one mark, with the later time.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: ID of the channel of the thread.
            thread_ts: Timestamp of the parent message of the thread.
            time: When the event came.
        """

        with self._database.begin() as connection: connection.execute(_THREAD_UPSERT, (workspace_id, channel_id, thread_ts, time.astimezone(datetime.UTC).isoformat()))

    def clear(
        self,
        workspace_id: str,
        time: datetime.datetime
    ) -> None:

        """Removes the marks of a workspace once a backup that loaded them has succeeded.

        A mark made again after `time` stays, as the backup may have fetched
        the thread before the event that marked it again.

        Args:
            workspace_id: Slack workspace ID.
            time: When the backup loaded the marks.
        """

        with self._database.begin() as connection: connection.execute(_THREAD_DELETE, (workspace_id, time.astimezone(datetime.UTC).isoformat()))
