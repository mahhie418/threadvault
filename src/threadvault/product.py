"""Name, command, summary and version of the product."""

import importlib.metadata

_DISTRIBUTION = importlib.metadata.distribution(__name__.partition('.')[0])
_SCRIPTS = _DISTRIBUTION.entry_points.select(group = 'console_scripts')

NAME = _DISTRIBUTION.metadata['Name']
SUMMARY = _DISTRIBUTION.metadata['Summary']
VERSION = _DISTRIBUTION.version
COMMAND = next(iter(_SCRIPTS)).name
