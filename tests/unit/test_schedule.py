import collections.abc
import datetime
import os
import pathlib

import pytest

import threadvault.schedule
import threadvault.storage

MOMENTS_FOLLOWED = [
    (datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC), '12:00', 'Asia/Tokyo', datetime.datetime(2026, 10, 10, 3, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC), '00:00', 'Asia/Tokyo', datetime.datetime(2026, 10, 10, 15, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC), '00:00', 'UTC', datetime.datetime(2026, 10, 10, 0, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 10, 0, 0, tzinfo = datetime.UTC), '20:00', 'America/Los_Angeles', datetime.datetime(2026, 10, 10, 3, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC), '00:00', 'Europe/London', datetime.datetime(2026, 10, 9, 23, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 3, 29, 0, 0, tzinfo = datetime.UTC), '01:30', 'Europe/London', datetime.datetime(2026, 3, 29, 1, 30, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 24, 23, 0, tzinfo = datetime.UTC), '01:30', 'Europe/London', datetime.datetime(2026, 10, 25, 0, 30, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 25, 0, 30, tzinfo = datetime.UTC), '01:30', 'Europe/London', datetime.datetime(2026, 10, 26, 1, 30, tzinfo = datetime.UTC))
]

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

@pytest.mark.parametrize(('moment', 'time', 'timezone', 'expected'), MOMENTS_FOLLOWED)
def test_schedule_time_following(
    moment: datetime.datetime,
    time: str,
    timezone: str,
    expected: datetime.datetime
) -> None:

    planned = threadvault.schedule.follow(moment, time, timezone)

    assert planned == expected
    assert planned.tzinfo == datetime.UTC

def test_schedule_time_store(
    database: threadvault.storage.Database
) -> None:

    calendar = threadvault.schedule.ScheduleIO(database)
    times = [datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC), datetime.datetime(2026, 10, 10, 15, 0, tzinfo = datetime.UTC)]

    assert calendar.load('xxx1') is None

    for time in times: calendar.save('xxx1', time)

    assert calendar.load('xxx1') == times[1]
    assert calendar.load('xxx2') is None
