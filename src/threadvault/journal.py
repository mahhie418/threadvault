# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Backups that have ended, which the App Home reports."""

import dataclasses
import datetime

import threadvault.storage

_RUN_SELECT = 'SELECT finish_time, repository_name, commit_id, error_message FROM backup WHERE workspace_id = ? ORDER BY run_id DESC LIMIT 1'
_RUN_INSERT = 'INSERT INTO backup (workspace_id, finish_time, repository_name, commit_id, error_message) VALUES (?, ?, ?, ?, ?)'

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Run:

    """One backup into the vault on GitHub, once it has ended.

    Attributes:
        completion: When the backup ended.
        repository: Repository of the vault, as owner/name.
        commit: Commit that the vault was at after the backup, or None when the backup failed.
        reason: Why the backup failed, or None when it succeeded.
    """

    completion: datetime.datetime
    repository: str
    commit: str | None
    reason: str | None

class RunIO:

    """Reads and writes the backups of each workspace in the database."""

    def __init__(
        self,
        database: threadvault.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the backups.
        """

        self._database = database

    def load(
        self,
        workspace_id: str
    ) -> Run | None:

        """Loads the last backup of a workspace.

        Args:
            workspace_id: Slack workspace ID.

        Returns:
            The backup that ended last, or None before the first one ends.
        """

        row = self._database.connect().execute(_RUN_SELECT, (workspace_id,)).fetchone()

        if row is None: return None

        return Run(completion = datetime.datetime.fromisoformat(row['finish_time']), repository = row['repository_name'], commit = row['commit_id'], reason = row['error_message'])

    def save(
        self,
        workspace_id: str,
        run: Run
    ) -> None:

        """Saves a backup of a workspace once it has ended, keeping the earlier ones.

        Args:
            workspace_id: Slack workspace ID.
            run: The backup.
        """

        with self._database.begin() as connection: connection.execute(_RUN_INSERT, (workspace_id, run.completion.isoformat(), run.repository, run.commit, run.reason))
