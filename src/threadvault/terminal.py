"""Command-line entry point."""

import argparse

import threadvault.encryption
import threadvault.product

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

    return parser

def _generate_key(
    _: argparse.Namespace
) -> int:

    print(threadvault.encryption.generate())

    return 0
