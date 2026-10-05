"""Attached files of messages, saved in the vault."""

import collections.abc
import datetime
import ntpath
import pathlib
import re
import typing
import unicodedata

import threadvault.vault.layout

ATTACHMENTS_DIRECTORY = 'attachments'

_MODES_EXCLUDED = frozenset({'external', 'hidden_by_limit', 'tombstone'})

_PATTERN_CHARACTERS_INVALID = re.compile(r'[\x00-\x1f\x7f"*/:<>?\\|\ud800-\udfff]')

def select(
    messages: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]]
) -> list[dict[str, typing.Any]]:

    """Picks the attached files of messages that the vault can save.

    A file that Slack hides for the limits of the plan, a deleted file, a file
    kept outside Slack and a file without a download address are left out.
    Each file comes once, however many messages share it.

    Args:
        messages: Messages as conversations.history and conversations.replies
                  return them.

    Returns:
        The files, as Slack describes them in the messages.
    """

    files: dict[str, dict[str, typing.Any]] = {}

    for message in messages:

        attached: list[dict[str, typing.Any]] = message.get('files', [])

        for file in attached:

            if file.get('mode') not in _MODES_EXCLUDED and 'url_private_download' in file: files[file['id']] = file

    return list(files.values())

def locate(
    file: collections.abc.Mapping[str, typing.Any]
) -> str:

    """Gives the place of an attached file in the vault.

    The file goes to a directory named after its ID, in the directory of the
    month in which it was uploaded, in UTC. It keeps its name from Slack in
    Unicode NFC, with the characters that some file systems reject replaced by
    underscores and the dots and spaces at the end dropped. A name longer than
    `threadvault.vault.layout.NAME_SIZE_MAXIMUM` bytes of UTF-8 is shortened
    before its extension. The name gets an underscore in front when Windows
    keeps it for devices, and is the ID of the file when nothing is left.

    Args:
        file: The file as Slack describes it in a message.

    Returns:
        The path from the root of the vault, with forward slashes.
    """

    month = datetime.datetime.fromtimestamp(file['created'], datetime.UTC).strftime('%Y-%m')

    return '/'.join((ATTACHMENTS_DIRECTORY, month, file['id'], _sanitise(file.get('name', '')) or file['id']))

def _sanitise(
    name: str
) -> str:

    name = _PATTERN_CHARACTERS_INVALID.sub('_', unicodedata.normalize('NFC', name)).rstrip('. ')
    parts = pathlib.PurePath(name)
    room = max(threadvault.vault.layout.NAME_SIZE_MAXIMUM - len(parts.suffix.encode('utf-8')), 0)
    name = parts.stem.encode('utf-8')[:room].decode('utf-8', errors = 'ignore') + parts.suffix

    return f'_{name}' if name and ntpath.isreserved(name) else name
