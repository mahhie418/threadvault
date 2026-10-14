# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""State file that keeps the layout of the vault between runs."""

import collections.abc
import json
import os
import pathlib

import threadvault.product
import threadvault.vault.layout

STATE_DIRECTORY = '.threadvault'
STATE_FILE = 'state.json'

FORMAT_VERSION = 1

class StateError(Exception):

    """Raised when the vault contains invalid state or unsafe paths."""

def load(
    vault: pathlib.Path
) -> dict[str, str]:

    """Reads the channel directories that the state file of a vault records.

    Args:
        vault: Root directory of the vault.

    Returns:
        Directory names by channel ID, empty when the vault has no state file yet.

    Raises:
        StateError: The state file is damaged or was written by a newer version.
    """

    path = pathlib.Path(os.path.join(vault, STATE_DIRECTORY, STATE_FILE))

    try: text = path.read_text(encoding = 'utf-8')
    except FileNotFoundError: return {}

    try: data = json.loads(text)
    except json.JSONDecodeError: raise StateError(f'{path} is not valid JSON') from None

    match data:

        case {'format_version': int() as version} if version > FORMAT_VERSION: raise StateError(f'{path} was written by a newer version of {threadvault.product.NAME}')
        case {'format_version': 1, 'directories': {**directories}} if all(isinstance(name, str) and threadvault.vault.layout.validate(name) for name in directories.values()): return directories
        case _: raise StateError(f'{path} is not a state file of {threadvault.product.NAME}')

def save(
    vault: pathlib.Path,
    directories: collections.abc.Mapping[str, str]
) -> None:

    """Writes the channel directories to the state file of a vault.

    The new file replaces the old one in a single step, so that a crash never
    leaves half a file behind.

    Args:
        vault: Root directory of the vault.
        directories: Directory names by channel ID.
    """

    path = pathlib.Path(os.path.join(vault, STATE_DIRECTORY, STATE_FILE))
    temporary = path.with_name(f'{path.name}.tmp')
    text = json.dumps({'directories': dict(directories), 'format_version': FORMAT_VERSION}, ensure_ascii = False, indent = 2, sort_keys = True)

    path.parent.mkdir(exist_ok = True)
    temporary.write_text(f'{text}\n', encoding = 'utf-8', newline = '\n')
    temporary.replace(path)
