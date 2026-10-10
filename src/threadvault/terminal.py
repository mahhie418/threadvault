"""Command-line entry point."""

import argparse
import contextlib
import datetime
import importlib.resources
import os
import pathlib
import sys

import slack_bolt.error
import slack_sdk.errors

import threadvault.backup.runner
import threadvault.configuration
import threadvault.customisation
import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.github.token
import threadvault.product
import threadvault.slack.api
import threadvault.slack.application
import threadvault.storage
import threadvault.vault.repository
import threadvault.vault.state

def main(
    arguments: list[str] | None = None
) -> int:

    """Runs the command.

    Args:
        arguments: Command-line arguments without the program name.
                   When None, the arguments of the current process are used.

    Returns:
        The exit status of the command.

    Raises:
        SystemExit: argparse handled the arguments itself:
                    it printed help or the version (status 0), or a usage error (status 2).
    """

    parser = _build()
    namespace = parser.parse_args(arguments)

    return namespace.handler(namespace)

def _build() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog = threadvault.product.COMMAND, description = threadvault.product.SUMMARY)
    parser.add_argument('--version', action = 'version', version = f'%(prog)s {threadvault.product.VERSION}')

    commands = parser.add_subparsers(title = 'commands', metavar = '<command>', required = True)
    encryption = commands.add_parser('generate-key', help = 'print a new key for THREADVAULT_SECRET_KEY')
    encryption.set_defaults(handler = _generate_key)
    backup = commands.add_parser('backup-now', help = 'back up the workspace once, into a local directory or a GitHub repository')
    backup.set_defaults(handler = _backup_now)
    destination = backup.add_mutually_exclusive_group(required = True)
    destination.add_argument('--out', type = pathlib.Path, help = 'directory of the vault', metavar = 'DIR')
    destination.add_argument('--repo', help = 'GitHub repository of the vault, created as private when missing', metavar = 'OWNER/NAME')
    login = commands.add_parser('github-login', help = 'connect GitHub with the device flow of the GitHub App')
    login.set_defaults(handler = _github_login)
    server = commands.add_parser('slack-serve', help = 'run the Slack app until it is stopped')
    server.set_defaults(handler = _slack_serve)
    manifest = commands.add_parser('print-manifest', help = 'print the manifest for creating the Slack app')
    manifest.set_defaults(handler = _print_manifest)

    return parser

def _generate_key(
    _: argparse.Namespace
) -> int:

    print(threadvault.encryption.generate())

    return 0

def _backup_now(
    namespace: argparse.Namespace
) -> int:

    now = datetime.datetime.now(datetime.UTC)
    repository: str | None = namespace.repo

    try:

        settings = threadvault.configuration.load()

        if repository is None: settings.require('slack_bot_token')
        else: settings.require('slack_bot_token', 'github_app_client_id')

        workspace = threadvault.customisation.Settings(repository_name = repository)
        client = threadvault.slack.api.connect(settings.slack_bot_token)

        if repository is None:

            results = threadvault.backup.runner.run(client, namespace.out, workspace, days = settings.threadvault_lookback_days, limit = settings.threadvault_deletions_maximum, now = now)

        else:

            cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
            database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))
            manager = threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id)
            directory = pathlib.Path(os.path.join(settings.threadvault_data_directory, 'vaults', *repository.split('/')))

            try: results = threadvault.backup.runner.publish(client, workspace, directory = directory, full_name = repository, token = lambda: manager.acquire(datetime.datetime.now(datetime.UTC)), days = settings.threadvault_lookback_days, limit = settings.threadvault_deletions_maximum, now = now)
            finally: database.close()

    except (threadvault.configuration.ConfigurationError, threadvault.customisation.SettingInvalidError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, threadvault.vault.state.StateError, threadvault.vault.repository.GitError, threadvault.github.token.TokenError, threadvault.github.rest.GitHubError, threadvault.backup.runner.VaultError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    for result in results: print(f'{result.directory}: {result.messages} messages, {result.deleted} deleted, {result.withheld} withheld, {result.files} files, {result.failures} failures')

    return 0

def _github_login(
    _: argparse.Namespace
) -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('github_app_client_id')
        cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
        code = threadvault.github.oauth.request(settings.github_app_client_id)

        print(f'Open {code.verification_uri} and enter {code.user_code}', flush = True)

        tokens = threadvault.github.oauth.poll(settings.github_app_client_id, code)
        database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))

        try: threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id).save(tokens)
        finally: database.close()

        login = threadvault.github.rest.user(tokens.access_token)['login']

    except (threadvault.configuration.ConfigurationError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, threadvault.github.oauth.OAuthError, threadvault.github.rest.GitHubError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    print(f'Connected to GitHub as {login}')

    return 0

def _slack_serve(
    _: argparse.Namespace
) -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'threadvault_owner_id', 'github_app_client_id', 'github_app_slug')

        with contextlib.suppress(KeyboardInterrupt): threadvault.slack.application.serve(settings)

    except (threadvault.configuration.ConfigurationError, threadvault.slack.application.LockError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, slack_bolt.error.BoltError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    return 0

def _print_manifest(
    _: argparse.Namespace
) -> int:

    print(importlib.resources.files('threadvault.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'), end = '')

    return 0
