"""Directory names that channels get in the vault."""

import collections
import collections.abc
import ntpath
import re
import unicodedata

NAME_SIZE_MAXIMUM = 200

_PATTERN_CHARACTERS_INVALID = re.compile(r'[\x00-\x1f\x7f"*./:<>?\\|\ud800-\udfff\s]')

def assign(
    channels: collections.abc.Mapping[str, str]
) -> dict[str, str]:

    """Gives each channel a directory name that every platform accepts.

    The name is the channel name in Unicode NFC, with the characters that some
    file systems reject replaced by underscores, cut to `NAME_SIZE_MAXIMUM`
    bytes of UTF-8. Channels whose names Windows keeps for devices, or whose
    names are equal apart from case, get `<name>-<channel ID>` instead,
    because Windows and macOS ignore case in file names. A channel without a
    name gets its ID.

    Args:
        channels: Channel names by channel ID.

    Returns:
        Directory names by channel ID.
    """

    bases = {channel: _sanitise(name) or channel for channel, name in channels.items()}
    names = dict(bases)

    while clashing := _verify(names, bases): names |= {channel: f'{bases[channel]}-{channel}' for channel in clashing}

    return names

def _sanitise(
    name: str
) -> str:

    name = _PATTERN_CHARACTERS_INVALID.sub('_', unicodedata.normalize('NFC', name))

    return name.encode('utf-8')[:NAME_SIZE_MAXIMUM].decode('utf-8', errors = 'ignore')

def _verify(
    names: collections.abc.Mapping[str, str],
    bases: collections.abc.Mapping[str, str]
) -> set[str]:

    counts = collections.Counter(name.casefold() for name in names.values())

    return {channel for channel, name in names.items() if name == bases[channel] and (counts[name.casefold()] > 1 or ntpath.isreserved(name))}
