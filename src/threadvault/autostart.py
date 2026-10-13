# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Start of the Slack app at login: a launchd agent on macOS and a scheduled task on Windows."""

import importlib.resources
import os
import pathlib
import subprocess
import sys
import xml.sax.saxutils

LABEL = 'threadvault'

PLATFORMS = frozenset({'darwin', 'win32'})

class AutostartError(Exception):

    """Raised when the start of the Slack app at login cannot be registered or removed."""

def register(
    log: pathlib.Path
) -> str:

    """Registers the Slack app to start at login, and again whenever it stops with an error.

    On macOS, a launchd agent of the user runs the Slack app with the Python
    of this installation and the PATH of the current process, so that it
    finds git, and appends the output to the log. On Windows, a scheduled
    task of the user runs it with the windowless Python of this installation,
    from a task file next to the log, and the Slack app appends its output to
    the log itself. Registration also starts the app immediately, stopping
    an earlier scheduled instance on Windows first.

    Args:
        log: File for the output of the Slack app.

    Returns:
        Where the registration is described.

    Raises:
        AutostartError: This system is not supported, or it refused the
                        registration.
    """

    if sys.platform == 'darwin': return _launch(log, os.getuid())
    if sys.platform == 'win32': return _schedule(log)

    raise AutostartError(f'Starting at login is not supported on {sys.platform}')

def unregister(
    log: pathlib.Path
) -> str | None:

    """Stops the Slack app that starts at login, and removes its registration.

    On macOS, the launchd agent is booted out, which stops the Slack app, and
    its file is deleted. On Windows, the running scheduled task is ended, and
    the task and its file next to the log are deleted.

    Args:
        log: File for the output of the Slack app.

    Returns:
        Where the registration was described, or None when there was none.

    Raises:
        AutostartError: This system is not supported, or it refused to delete
                        the registration.
    """

    if sys.platform == 'darwin': return _unload(os.getuid())
    if sys.platform == 'win32': return _cancel(log)

    raise AutostartError(f'Removing the start at login is not supported on {sys.platform}')

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

def _schedule(
    log: pathlib.Path
) -> str:

    task = pathlib.Path(os.path.join(log.parent, f'{LABEL}.xml'))
    task.parent.mkdir(parents = True, exist_ok = True)
    task.write_text(_fill('task.xml', user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}", python = str(pathlib.Path(sys.executable).with_name('pythonw.exe')), module = __name__.partition('.')[0], log = subprocess.list2cmdline([str(log)])), encoding = 'utf-16')

    command = os.path.join(os.environ.get('SYSTEMROOT', 'C:\\Windows'), 'System32', 'schtasks.exe')

    try: subprocess.run([command, '/Create', '/TN', LABEL, '/XML', str(task), '/F'], capture_output = True, encoding = 'utf-8', errors = 'replace', check = True)
    except subprocess.CalledProcessError as error: raise AutostartError(f'Task Scheduler refused {task}: {error.stderr.strip()}') from None

    subprocess.run([command, '/End', '/TN', LABEL], capture_output = True, check = False)

    try: subprocess.run([command, '/Run', '/TN', LABEL], capture_output = True, encoding = 'utf-8', errors = 'replace', check = True)
    except subprocess.CalledProcessError as error: raise AutostartError(f'Task Scheduler could not start {LABEL}: {error.stderr.strip()}') from None

    return str(task)

def _unload(
    user: int
) -> str | None:

    agent = pathlib.Path(os.path.join(pathlib.Path.home(), 'Library', 'LaunchAgents', f'{LABEL}.plist'))

    subprocess.run(['/bin/launchctl', 'bootout', f'gui/{user}/{LABEL}'], capture_output = True, check = False)

    if not agent.exists(): return None

    agent.unlink()

    return str(agent)

def _cancel(
    log: pathlib.Path
) -> str | None:

    task = pathlib.Path(os.path.join(log.parent, f'{LABEL}.xml'))
    command = os.path.join(os.environ.get('SYSTEMROOT', 'C:\\Windows'), 'System32', 'schtasks.exe')

    if subprocess.run([command, '/Query', '/TN', LABEL], capture_output = True, check = False).returncode != 0: return None

    subprocess.run([command, '/End', '/TN', LABEL], capture_output = True, check = False)

    try: subprocess.run([command, '/Delete', '/TN', LABEL, '/F'], capture_output = True, encoding = 'utf-8', errors = 'replace', check = True)
    except subprocess.CalledProcessError as error: raise AutostartError(f'Task Scheduler refused to delete {LABEL}: {error.stderr.strip()}') from None

    task.unlink(missing_ok = True)

    return str(task)

def _fill(
    name: str,
    **values: str
) -> str:

    template = importlib.resources.files('threadvault').joinpath('templates', name).read_text(encoding = 'utf-8')

    return template.format(**{key: xml.sax.saxutils.escape(value) for key, value in values.items()})
