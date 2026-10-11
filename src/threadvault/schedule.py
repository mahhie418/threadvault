"""Times of the daily backup, kept in the wall-clock time of the workspace."""

import datetime
import zoneinfo

import threadvault.storage

_SCHEDULE_SELECT = 'SELECT run_time FROM schedule WHERE workspace_id = ?'

_SCHEDULE_UPSERT = """
    INSERT INTO schedule (workspace_id, run_time)
    VALUES (?, ?)
    ON CONFLICT (workspace_id) DO UPDATE SET
        run_time = excluded.run_time
"""

def follow(
    moment: datetime.datetime,
    time: str,
    timezone: str
) -> datetime.datetime:

    """Gives the first time of the daily backup after a moment.

    The backup keeps its wall-clock time in the time zone across daylight
    saving changes. On a day when the clocks skip the time, the backup runs
    as much later as the clocks moved, and on a day when they repeat it, the
    backup runs the first time only.

    Args:
        moment: The moment, with its time zone.
        time: Time of the daily backup as HH:MM.
        timezone: IANA time zone of `time`.

    Returns:
        The time of the backup, in UTC.
    """

    zone = zoneinfo.ZoneInfo(timezone)
    clock = datetime.time.fromisoformat(time)
    day = moment.astimezone(zone).date()
    candidate = datetime.datetime.combine(day, clock, tzinfo = zone)

    if candidate <= moment: candidate = datetime.datetime.combine(day + datetime.timedelta(days = 1), clock, tzinfo = zone)

    return candidate.astimezone(datetime.UTC)

class ScheduleIO:

    """Reads and writes the time of the next daily backup of each workspace in the database."""

    def __init__(
        self,
        database: threadvault.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the times.
        """

        self._database = database

    def load(
        self,
        workspace_id: str
    ) -> datetime.datetime | None:

        """Loads the time of the next daily backup of a workspace.

        Args:
            workspace_id: Slack workspace ID.

        Returns:
            The time, or None before one is planned.
        """

        row = self._database.connect().execute(_SCHEDULE_SELECT, (workspace_id,)).fetchone()

        if row is None: return None

        return datetime.datetime.fromisoformat(row['run_time'])

    def save(
        self,
        workspace_id: str,
        time: datetime.datetime
    ) -> None:

        """Saves the time of the next daily backup of a workspace, replacing the earlier one.

        Args:
            workspace_id: Slack workspace ID.
            time: The time.
        """

        with self._database.begin() as connection: connection.execute(_SCHEDULE_UPSERT, (workspace_id, time.isoformat()))
