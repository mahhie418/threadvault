"""Slack app of the admins, connected to Slack through Socket Mode."""

import collections.abc
import contextlib
import datetime
import os
import pathlib
import sqlite3
import time

import slack_bolt
import slack_bolt.adapter.socket_mode
import slack_sdk

import threadvault.configuration
import threadvault.encryption
import threadvault.github.token
import threadvault.product
import threadvault.slack.api
import threadvault.slack.handler
import threadvault.storage

LOCK_FILE = 'serve.lock'

SCHEDULE_INTERVAL = 60

class LockError(Exception):

    """Raised when another app already serves with the same data directory."""

def build(
    client: slack_sdk.web.WebClient,
    settings: threadvault.configuration.Settings,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]:

    """Builds the Slack app with its listeners.

    Args:
        client: Slack client with the bot token.
        settings: Settings of the deployment.
        database: Database with the settings of each workspace.
        manager: GitHub tokens of the deployment.

    Returns:
        The app, and the function that starts the daily backup once it is
        due, given the workspace ID and the current time.

    Raises:
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    application = slack_bolt.App(token = client.token, client = client)

    return application, threadvault.slack.handler.register(application, settings, database, manager)

@contextlib.contextmanager
def lock(
    directory: pathlib.Path
) -> collections.abc.Generator[None]:

    """Holds the lock file in the data directory while the app serves.

    A second Socket Mode connection would split the events and the button
    presses between two apps, so only one app may serve with a data
    directory. The lock file is a SQLite database held in an exclusive
    transaction, which works alike on every operating system, and the lock
    goes when the process ends, even when it crashes.

    Args:
        directory: Data directory of the app, created when missing.

    Yields:
        Nothing; the lock is held until the block ends.

    Raises:
        LockError: Another app holds the lock.
    """

    directory.mkdir(parents = True, exist_ok = True)

    connection = sqlite3.connect(pathlib.Path(os.path.join(directory, LOCK_FILE)), timeout = 0, autocommit = True)

    try:

        try: connection.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError: raise LockError(f'{threadvault.product.NAME} is already running with the data directory {directory}') from None

        yield

    finally:

        connection.close()

def serve(
    settings: threadvault.configuration.Settings
) -> None:

    """Serves the Slack app until the process stops.

    Args:
        settings: Settings of the deployment, with the bot and app-level tokens.

    Raises:
        LockError: Another app already serves with the data directory.
        threadvault.encryption.SecretKeyError: The secret key cannot be used.
        threadvault.storage.DatabaseError: The database cannot be used.
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    with lock(settings.threadvault_data_directory):

        cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
        database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))
        manager = threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id)

        try:

            application, schedule = build(threadvault.slack.api.connect(settings.slack_bot_token), settings, database, manager)
            start(application, settings.slack_app_token, schedule)

        finally:

            database.close()

def start(
    application: slack_bolt.App,
    token: str,
    schedule: collections.abc.Callable[[str, datetime.datetime], None]
) -> None:

    """Connects the app to Slack through Socket Mode and serves it until the process stops.

    Meanwhile, the daily backup is checked every `SCHEDULE_INTERVAL` seconds
    against the clock rather than waited for, so that a backup missed while
    the computer slept runs once it wakes.

    Args:
        application: The application.
        token: App-level token of the Slack app (xapp-...).
        schedule: Function that starts the daily backup once it is due, given
                  the workspace ID and the current time.
    """

    slack_bolt.adapter.socket_mode.SocketModeHandler(application, token).connect()
    team = application.client.auth_test().get('team_id', '')

    while True: schedule(team, datetime.datetime.now(datetime.UTC)); time.sleep(SCHEDULE_INTERVAL)
