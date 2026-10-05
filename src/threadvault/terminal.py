"""Command-line entry point."""

import argparse
import datetime
import pathlib
import sys

import slack_sdk.errors

import threadvault.backup.runner
import threadvault.configuration
import threadvault.customisation
import threadvault.encryption
import threadvault.product
import threadvault.slack.api
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
    backup = commands.add_parser('backup-now', help = 'back up the workspace once into a local directory')
    backup.add_argument('--out', type = pathlib.Path, required = True, help = 'directory of the vault', metavar = 'DIR')
    backup.set_defaults(handler = _backup_now)

    return parser

def _generate_key(
    _: argparse.Namespace
) -> int:

    print(threadvault.encryption.generate())

    return 0

def _backup_now(
    namespace: argparse.Namespace
) -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('slack_bot_token')
        client = threadvault.slack.api.connect(settings.slack_bot_token)
        results = threadvault.backup.runner.run(client, namespace.out, threadvault.customisation.Settings(), days = settings.threadvault_lookback_days, limit = settings.threadvault_deletions_maximum, now = datetime.datetime.now(datetime.UTC))

    except (threadvault.configuration.ConfigurationError, threadvault.vault.state.StateError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    for result in results: print(f'{result.directory}: {result.messages} messages, {result.deleted} deleted, {result.withheld} withheld, {result.files} files, {result.failures} failures')

    return 0
