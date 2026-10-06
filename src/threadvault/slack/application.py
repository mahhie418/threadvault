"""Slack app of the admins, connected to Slack through Socket Mode."""

import collections.abc
import contextlib
import os
import pathlib
import sqlite3

import slack_bolt
import slack_bolt.adapter.socket_mode
import slack_sdk

import threadvault.configuration
import threadvault.product
import threadvault.slack.api

LOCK_FILE = 'serve.lock'

class LockError(Exception):

    """Raised when another app already serves with the same data directory."""

def build(
    client: slack_sdk.web.WebClient
) -> slack_bolt.App:

    """Builds the Slack app.

    Args:
        client: Slack client with the bot token.

    Returns:
        The app.

    Raises:
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    return slack_bolt.App(token = client.token, client = client)

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
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    with lock(settings.threadvault_data_directory): start(build(threadvault.slack.api.connect(settings.slack_bot_token)), settings.slack_app_token)

def start(
    application: slack_bolt.App,
    token: str
) -> None:

    """Connects the app to Slack through Socket Mode and serves it until the process stops.

    Args:
        application: The application.
        token: App-level token of the Slack app (xapp-...).
    """

    slack_bolt.adapter.socket_mode.SocketModeHandler(application, token).start()
