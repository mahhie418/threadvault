import os
import pathlib
import plistlib
import subprocess
import sys
import unittest.mock
import xml.sax.saxutils

import pytest

import threadvault.autostart

def test_autostart_agent_registration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    log = pathlib.Path(os.path.join(tmp_path, 'xxx&xxx.log'))
    run = unittest.mock.Mock()

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(os, 'getuid', lambda: 501, raising = False)
    monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(subprocess, 'run', run)

    agent = pathlib.Path(threadvault.autostart.register(log))

    assert agent == pathlib.Path(os.path.join(tmp_path, 'Library', 'LaunchAgents', 'threadvault.plist'))
    assert plistlib.loads(agent.read_bytes()) == {'Label': 'threadvault', 'ProgramArguments': [sys.executable, '-m', 'threadvault', 'start'], 'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False}, 'EnvironmentVariables': {'PATH': os.environ.get('PATH', '')}, 'StandardOutPath': str(log), 'StandardErrorPath': str(log)}
    assert [call.args[0] for call in run.call_args_list] == [['/bin/launchctl', 'bootout', 'gui/501/threadvault'], ['/bin/launchctl', 'bootstrap', 'gui/501', str(agent)]]

def test_autostart_agent_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(os, 'getuid', lambda: 501, raising = False)
    monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(subprocess, 'run', unittest.mock.Mock(side_effect = [None, subprocess.CalledProcessError(5, 'xxx', stderr = 'xxx\n')]))

    with pytest.raises(threadvault.autostart.AutostartError, match = r'refused .*threadvault\.plist: xxx$'): threadvault.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_task_registration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    log = pathlib.Path(os.path.join(tmp_path, 'xxx xxx.log'))
    run = unittest.mock.Mock()
    python = xml.sax.saxutils.escape(str(pathlib.Path(sys.executable).with_name('pythonw.exe')))

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('SYSTEMROOT', 'xxx')
    monkeypatch.setenv('USERDOMAIN', 'xxx1')
    monkeypatch.setenv('USERNAME', 'xxx2')
    monkeypatch.setattr(subprocess, 'run', run)

    task = pathlib.Path(threadvault.autostart.register(log))
    text = task.read_text(encoding = 'utf-16')

    assert task == pathlib.Path(os.path.join(tmp_path, 'threadvault.xml'))
    assert text.startswith('<?xml version="1.0" encoding="UTF-16"?>\n<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n')
    assert '<LogonTrigger>\n      <UserId>xxx1\\xxx2</UserId>\n    </LogonTrigger>' in text
    assert '<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>' in text
    assert '<RestartOnFailure>\n      <Interval>PT1M</Interval>\n      <Count>999</Count>\n    </RestartOnFailure>' in text
    assert f'<Exec>\n      <Command>{python}</Command>\n      <Arguments>-m threadvault start --log "{log}"</Arguments>\n    </Exec>' in text

    command = os.path.join('xxx', 'System32', 'schtasks.exe')

    assert [call.args[0] for call in run.call_args_list] == [[command, '/Create', '/TN', 'threadvault', '/XML', str(task), '/F'], [command, '/End', '/TN', 'threadvault'], [command, '/Run', '/TN', 'threadvault']]

def test_autostart_task_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', unittest.mock.Mock(side_effect = subprocess.CalledProcessError(1, 'xxx', stderr = 'xxx\n')))

    with pytest.raises(threadvault.autostart.AutostartError, match = r'refused .*threadvault\.xml: xxx$'): threadvault.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_start_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    run = unittest.mock.Mock(side_effect = [None, None, subprocess.CalledProcessError(1, 'xxx', stderr = 'xxx\n')])
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', run)

    with pytest.raises(threadvault.autostart.AutostartError, match = 'could not start threadvault: xxx'): threadvault.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_end_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    run = unittest.mock.Mock(side_effect = [None, subprocess.CompletedProcess('xxx', 1), None])
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', run)
    threadvault.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

    assert run.call_args_list[-1].args[0][1:] == ['/Run', '/TN', 'threadvault']
    assert len(run.call_args_list) == 3

def test_autostart_platform_support() -> None:

    assert sorted(threadvault.autostart.PLATFORMS) == ['darwin', 'win32']

def test_autostart_platform_rejection(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'xxx')

    with pytest.raises(threadvault.autostart.AutostartError, match = r'not supported on xxx$'): threadvault.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))
