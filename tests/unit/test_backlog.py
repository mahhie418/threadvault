import collections.abc
import datetime
import os
import pathlib

import pytest

import threadvault.backup.backlog
import threadvault.storage

TIME_MARKED = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

def test_backlog_thread_store(
    database: threadvault.storage.Database
) -> None:

    backlog = threadvault.backup.backlog.BacklogIO(database)

    assert backlog.load('TXXX1') == threadvault.backup.backlog.Backlog()

    for team, channel, thread_ts in (('TXXX1', 'CXXX1', '100.0'), ('TXXX1', 'CXXX1', '200.0'), ('TXXX1', 'CXXX2', '100.0'), ('TXXX2', 'CXXX1', '300.0')): backlog.mark(team, channel, thread_ts, TIME_MARKED)

    assert backlog.load('TXXX1') == threadvault.backup.backlog.Backlog(threads = {'CXXX1': frozenset({'100.0', '200.0'}), 'CXXX2': frozenset({'100.0'})})

def test_backlog_thread_clearance(
    database: threadvault.storage.Database
) -> None:

    backlog = threadvault.backup.backlog.BacklogIO(database)

    for team, thread_ts in (('TXXX1', '100.0'), ('TXXX1', '200.0'), ('TXXX2', '300.0')): backlog.mark(team, 'CXXX1', thread_ts, TIME_MARKED)

    backlog.mark('TXXX1', 'CXXX1', '200.0', TIME_MARKED + datetime.timedelta(hours = 1))
    backlog.clear('TXXX1', TIME_MARKED, ('CXXX1',))

    assert backlog.load('TXXX1') == threadvault.backup.backlog.Backlog(threads = {'CXXX1': frozenset({'200.0'})})
    assert backlog.load('TXXX2') == threadvault.backup.backlog.Backlog(threads = {'CXXX1': frozenset({'300.0'})})

def test_backlog_day_store(
    database: threadvault.storage.Database
) -> None:

    backlog = threadvault.backup.backlog.BacklogIO(database)

    for team, channel, day in (('TXXX1', 'CXXX1', datetime.date(2026, 10, 9)), ('TXXX1', 'CXXX1', datetime.date(2026, 10, 10)), ('TXXX1', 'CXXX2', datetime.date(2026, 10, 9)), ('TXXX2', 'CXXX1', datetime.date(2026, 10, 9))): backlog.mark(team, channel, day, TIME_MARKED)

    assert backlog.load('TXXX1') == threadvault.backup.backlog.Backlog(days = {'CXXX1': frozenset({datetime.date(2026, 10, 9), datetime.date(2026, 10, 10)}), 'CXXX2': frozenset({datetime.date(2026, 10, 9)})})

def test_backlog_day_clearance(
    database: threadvault.storage.Database
) -> None:

    backlog = threadvault.backup.backlog.BacklogIO(database)

    for team, day in (('TXXX1', datetime.date(2026, 10, 9)), ('TXXX1', datetime.date(2026, 10, 10)), ('TXXX2', datetime.date(2026, 10, 9))): backlog.mark(team, 'CXXX1', day, TIME_MARKED)

    backlog.mark('TXXX1', 'CXXX1', datetime.date(2026, 10, 10), TIME_MARKED + datetime.timedelta(hours = 1))
    backlog.clear('TXXX1', TIME_MARKED, ('CXXX1',))

    assert backlog.load('TXXX1') == threadvault.backup.backlog.Backlog(days = {'CXXX1': frozenset({datetime.date(2026, 10, 10)})})
    assert backlog.load('TXXX2') == threadvault.backup.backlog.Backlog(days = {'CXXX1': frozenset({datetime.date(2026, 10, 9)})})
