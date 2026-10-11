"""Start of the Slack app at login: a launchd agent on macOS."""

import importlib.resources
import os
import pathlib
import subprocess
import sys
import xml.sax.saxutils

LABEL = 'threadvault'

PLATFORMS = frozenset({'darwin'})

class AutostartError(Exception):

    """Raised when the Slack app cannot be registered to start at login."""

def register(
    log: pathlib.Path
) -> str:

    """Registers the Slack app to start at login, and again whenever it stops with an error.

    On macOS, a launchd agent of the user runs the Slack app with the Python
    of this installation and the PATH of the current process, so that it
    finds git, and appends the output to the log.

    Args:
        log: File for the output of the Slack app.

    Returns:
        Where the registration is described.

    Raises:
        AutostartError: This system is not supported, or it refused the
                        registration.
    """

    if sys.platform == 'darwin': return _launch(log, os.getuid())

    raise AutostartError(f'Starting at login is not supported on {sys.platform}')

def _launch(
    log: pathlib.Path,
    user: int
) -> str:

    agent = pathlib.Path(os.path.join(pathlib.Path.home(), 'Library', 'LaunchAgents', f'{LABEL}.plist'))
    agent.parent.mkdir(parents = True, exist_ok = True)
    agent.write_text(_fill('agent.plist', label = LABEL, python = sys.executable, module = __name__.partition('.')[0], path = os.environ.get('PATH', ''), log = str(log)), encoding = 'utf-8')

    subprocess.run(['/bin/launchctl', 'bootout', f'gui/{user}/{LABEL}'], capture_output = True, check = False)

    try: subprocess.run(['/bin/launchctl', 'bootstrap', f'gui/{user}', str(agent)], capture_output = True, encoding = 'utf-8', check = True)
    except subprocess.CalledProcessError as error: raise AutostartError(f'launchd refused {agent}: {error.stderr.strip()}') from None

    return str(agent)

def _fill(
    name: str,
    **values: str
) -> str:

    template = importlib.resources.files('threadvault').joinpath('templates', name).read_text(encoding = 'utf-8')

    return template.format(**{key: xml.sax.saxutils.escape(value) for key, value in values.items()})
