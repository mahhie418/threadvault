"""SQLite storage for data kept between runs, such as workspace settings."""

import collections.abc
import contextlib
import itertools
import pathlib
import sqlite3
import threading

import threadvault.product

DATABASE_FILE = 'threadvault.sqlite3'
TIMEOUT_LIMIT = 10.

_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        """
        CREATE TABLE slack (
            workspace_id TEXT PRIMARY KEY,
            configuration_data TEXT NOT NULL,
            update_user TEXT NOT NULL,
            update_time TEXT NOT NULL
        ) STRICT
        """,
    ),
    (
        """
        CREATE TABLE github (
            credential_id INTEGER PRIMARY KEY CHECK (credential_id = 1),
            credential_data TEXT NOT NULL,
            update_time TEXT NOT NULL
        ) STRICT
        """,
    ),
    (
        """
        CREATE TABLE backup (
            run_id INTEGER PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            finish_time TEXT NOT NULL,
            repository_name TEXT NOT NULL,
            commit_id TEXT,
            error_message TEXT
        ) STRICT
        """,
    ),
)

class DatabaseError(Exception):

    """Raised when this version of the product cannot use the database."""

class Database:

    """One SQLite database file with a separate connection for each thread.

    SQLite connections must not be shared between threads, and the bot runs
    Slack handlers, the backup worker and GitHub polling on different threads.

    Attributes:
        path: Location of the database file.
    """

    def __init__(
        self,
        path: pathlib.Path
    ) -> None:

        """Opens the database, creating it and applying migrations as needed.

        Args:
            path: Location of the database file.
                  Missing parent directories are created with owner-only permissions.

        Raises:
            DatabaseError: The database was created by a newer version.
        """

        self.path = path

        self._local = _Local()

        path.parent.mkdir(mode = 0o700, parents = True, exist_ok = True)

        try: self._migrate()
        except BaseException: self.close(); raise

    def connect(
        self
    ) -> sqlite3.Connection:

        """Returns the calling thread's connection, opening it on first use."""

        if self._local.connection is None: self._local.connection = self._open()

        return self._local.connection

    @contextlib.contextmanager
    def begin(
        self
    ) -> collections.abc.Generator[sqlite3.Connection]:

        """Runs the block in a write transaction.

        The transaction commits when the block finishes and rolls back when
        the block raises.

        Yields:
            The calling thread's connection, inside the transaction.
        """

        connection = self.connect()
        connection.execute('BEGIN IMMEDIATE')

        try: yield connection
        except BaseException: connection.execute('ROLLBACK'); raise

        connection.execute('COMMIT')

    def close(
        self
    ) -> None:

        """Closes the calling thread's connection, if it has one."""

        if self._local.connection is not None: self._local.connection.close(); self._local.connection = None

    def _open(
        self
    ) -> sqlite3.Connection:

        connection = sqlite3.connect(self.path, timeout = TIMEOUT_LIMIT, autocommit = True)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA journal_mode = WAL')
        connection.execute('PRAGMA synchronous = NORMAL')
        connection.execute('PRAGMA foreign_keys = ON')

        return connection

    def _migrate(
        self
    ) -> None:

        with self.begin() as connection:

            version = connection.execute('PRAGMA user_version').fetchone()[0]

            if version > len(_MIGRATIONS): raise DatabaseError(f'{self.path} was created by a newer version of {threadvault.product.NAME}')

            for statement in itertools.chain.from_iterable(_MIGRATIONS[version:]): connection.execute(statement)

            connection.execute(f'PRAGMA user_version = {len(_MIGRATIONS)}')

class _Local(threading.local):

    connection: sqlite3.Connection | None = None
