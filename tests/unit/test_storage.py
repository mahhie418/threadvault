import collections.abc
import os
import pathlib
import sqlite3
import threading

import pytest

import threadvault.storage

TABLES = {'slack', 'github'}
INSERT = "INSERT INTO slack VALUES ('xxx', 'xxx', 'xxx', 'xxx')"

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, 'xxx', threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

def count(
    database: threadvault.storage.Database
) -> int:

    return database.connect().execute('SELECT count(*) FROM slack').fetchone()[0]

def insert(
    database: threadvault.storage.Database
) -> None:

    with database.begin() as connection: connection.execute(INSERT); raise RuntimeError('xxx')

def test_storage_database_creation(
    database: threadvault.storage.Database
) -> None:

    connection = database.connect()
    rows = connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()

    assert TABLES.issubset(row['name'] for row in rows)
    assert connection.execute('PRAGMA user_version').fetchone()[0] >= 1

def test_storage_database_connection(
    database: threadvault.storage.Database
) -> None:

    connection = database.connect()

    assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1

def test_storage_database_consistency(
    database: threadvault.storage.Database
) -> None:

    connections: list[sqlite3.Connection] = []

    def work() -> None:

        connections.append(database.connect())
        database.close()

    worker = threading.Thread(target = work)
    worker.start()
    worker.join()

    assert len(connections) == 1
    assert connections[0] is not database.connect()

def test_storage_database_robustness(
    tmp_path: pathlib.Path
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))
    databases = [threadvault.storage.Database(path) for _ in range(2)]

    with databases[0].begin() as connection: connection.execute(INSERT)
    databases[0].close()

    try: assert count(databases[1]) == 1
    finally: databases[1].close()

def test_storage_database_exception(
    database: threadvault.storage.Database
) -> None:

    with pytest.raises(RuntimeError, match = 'xxx'): insert(database)

    assert count(database) == 0

def test_storage_database_version(
    tmp_path: pathlib.Path
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))
    opening = threadvault.storage.Database(path)

    connection = opening.connect()
    connection.execute('PRAGMA user_version = 999')

    opening.close()

    with pytest.raises(threadvault.storage.DatabaseError, match = 'newer version'): threadvault.storage.Database(path)

def test_storage_directory_creation(
    tmp_path: pathlib.Path,
    database: threadvault.storage.Database
) -> None:

    expected = pathlib.Path(os.path.join(tmp_path, 'xxx', threadvault.storage.DATABASE_FILE))

    assert database.path == expected
    assert database.path.is_file()
