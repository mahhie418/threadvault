"""Directory names that channels get in the vault."""

import collections
import collections.abc
import ntpath
import re
import unicodedata

NAME_SIZE_MAXIMUM = 200

_PATTERN_CHARACTERS_INVALID = re.compile(r'[\x00-\x1f\x7f"*./:<>?\\|\ud800-\udfff\s]')

def assign(
    channels: collections.abc.Mapping[str, str],
    directories: collections.abc.Mapping[str, str]
) -> dict[str, str]:

    """Gives each channel a directory name that every platform accepts.

    A channel keeps the directory it already has unless its name changed. A
    channel that is no longer listed keeps its directory too, so that no other
    channel takes it over. Comparing the result with `directories` shows the
    directories to move.

    A new or renamed channel gets its name in Unicode NFC, with the characters
    that some file systems reject replaced by underscores, cut to
    `NAME_SIZE_MAXIMUM` bytes of UTF-8, or its ID when the name is empty. The
    name gets `-<channel ID>` when Windows keeps it for devices, or when it
    equals the name of another such channel apart from case, because Windows
    and macOS ignore case in file names. It gets `-<channel ID>` again while
    it equals a directory in use.

    Args:
        channels: Channel names by channel ID.
        directories: Directory names by channel ID from earlier runs.

    Returns:
        Directory names by channel ID, for the channels in either argument.
    """

    bases = {channel: _sanitise(name) or channel for channel, name in channels.items()}
    pasts = {channel: directory for channel, directory in directories.items() if channel not in bases or _fit(directory, bases[channel], channel)}
    names = {channel: base for channel, base in bases.items() if channel not in pasts}

    while clashing := _verify(names, bases, pasts.values()): names |= {channel: f'{names[channel]}-{channel}' for channel in clashing}

    return pasts | names

def _sanitise(
    name: str
) -> str:

    name = _PATTERN_CHARACTERS_INVALID.sub('_', unicodedata.normalize('NFC', name))

    return name.encode('utf-8')[:NAME_SIZE_MAXIMUM].decode('utf-8', errors = 'ignore')

def _fit(
    directory: str,
    base: str,
    channel: str
) -> bool:

    while directory != base and directory.endswith(f'-{channel}'): directory = directory.removesuffix(f'-{channel}')

    return directory == base

def _verify(
    names: collections.abc.Mapping[str, str],
    bases: collections.abc.Mapping[str, str],
    pasts: collections.abc.Iterable[str]
) -> set[str]:

    reserved = {directory.casefold() for directory in pasts}
    counts = collections.Counter(name.casefold() for name in names.values())

    return {channel for channel, name in names.items() if name.casefold() in reserved or ntpath.isreserved(name) or (name == bases[channel] and counts[name.casefold()] > 1)}
