"""Command-line entry point."""

import argparse

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
    parser.add_subparsers(title = 'commands', metavar = '<command>', required = True)
    parser.add_argument('--version', action = 'version', version = f'%(prog)s {threadvault.product.VERSION}')

    return parser
