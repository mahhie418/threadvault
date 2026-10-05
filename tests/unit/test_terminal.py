import os
import pathlib

import cryptography.fernet
import pytest
import slack_sdk

import threadvault.product
import threadvault.slack.api
import threadvault.terminal

TOKENS_BACKUP = [
    ('xoxb-xxx', 0, 'xxx: 0 messages, 0 deleted, 0 withheld, 0 files, 0 failures\ngeneral: 5 messages, 0 deleted, 0 withheld, 0 files, 0 failures\n', ''),
    ('', 1, '', 'error: Missing required environment variables: SLACK_BOT_TOKEN\n')
]

def test_terminal_version(
    capsys: pytest.CaptureFixture[str]
) -> None:

    expected = f'{threadvault.product.COMMAND} {threadvault.product.VERSION}'

    with pytest.raises(SystemExit) as exception: threadvault.terminal.main(['--version'])

    assert exception.value.code == 0
    assert capsys.readouterr().out.strip() == expected

def test_terminal_missing(
    capsys: pytest.CaptureFixture[str]
) -> None:

    with pytest.raises(SystemExit) as exception: threadvault.terminal.main([])

    assert exception.value.code == 2
    assert 'required: <command>' in capsys.readouterr().err

def test_terminal_command_generate_key(
    capsys: pytest.CaptureFixture[str]
) -> None:

    assert threadvault.terminal.main(['generate-key']) == 0

    cryptography.fernet.Fernet(capsys.readouterr().out.strip())

@pytest.mark.parametrize(('token', 'status', 'out', 'err'), TOKENS_BACKUP)
def test_terminal_command_backup_now(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slack: slack_sdk.web.WebClient,
    token: str,
    status: int,
    out: str,
    err: str
) -> None:

    def connect(
        _: str
    ) -> slack_sdk.web.WebClient:

        return slack

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', token)
    monkeypatch.setattr(threadvault.slack.api, 'connect', connect)

    assert threadvault.terminal.main(['backup-now', '--out', os.path.join(tmp_path, 'xxx')]) == status
    assert capsys.readouterr() == (out, err)
