"""Backups that run in the background, one at a time."""

import collections.abc
import threading

class Worker:

    """Runs one backup at a time, away from the listeners of the app.

    A listener must answer Slack within 3 seconds while a backup takes
    minutes, so each backup runs in a thread of its own. A second backup does
    not start while one runs, because both would write the same clone of the
    vault.
    """

    def __init__(
        self,
        detach: collections.abc.Callable[[collections.abc.Callable[[], None]], None]
    ) -> None:

        """Initialises the worker, which runs nothing until a backup starts.

        Args:
            detach: Function that runs a function in a thread of its own.
        """

        self._detach = detach
        self._lock = threading.Lock()

    def busy(
        self
    ) -> bool:

        """Tells whether a backup is running.

        Returns:
            True while a backup runs.
        """

        return self._lock.locked()

    def start(
        self,
        backup: collections.abc.Callable[[], None],
        finish: collections.abc.Callable[[], None]
    ) -> bool:

        """Starts a backup, unless one is running.

        Args:
            backup: The backup.
            finish: Function called once the backup has ended, when the worker is free again.

        Returns:
            True when the backup started, or False when another one was running.
        """

        if not self._lock.acquire(blocking = False): return False

        def run() -> None:

            try: backup()
            finally: self._lock.release(); finish()

        self._detach(run)

        return True
