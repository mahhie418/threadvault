import collections.abc
import datetime
import os
import pathlib

import pytest

import threadvault.journal
import threadvault.storage

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

def test_journal_run_store(
    database: threadvault.storage.Database
) -> None:

    journal = threadvault.journal.RunIO(database)

    runs = [
        threadvault.journal.Run(completion = datetime.datetime(2026, 10, 8, 15, 0, tzinfo = datetime.UTC), repository = 'xxx/xxx1', commit = 'xxx', reason = None),
        threadvault.journal.Run(completion = datetime.datetime(2026, 10, 8, 15, 0, tzinfo = datetime.UTC), repository = 'xxx/xxx2', commit = None, reason = 'xxx')
    ]

    assert journal.load('xxx1') is None

    for run in runs: journal.save('xxx1', run)

    assert journal.load('xxx1') == runs[1]
    assert journal.load('xxx2') is None
