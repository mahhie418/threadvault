import json
import os
import pathlib

import cryptography.fernet
import pytest
import respx
import slack_sdk

import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.product
import threadvault.slack.api
import threadvault.storage
import threadvault.terminal

TOKENS_BACKUP = [
    ('xoxb-xxx', 0, 'xxx: 0 messages, 0 deleted, 0 withheld, 0 files, 0 failures\ngeneral: 5 messages, 0 deleted, 0 withheld, 0 files, 0 failures\n', ''),
    ('', 1, '', 'error: Missing required environment variables: SLACK_BOT_TOKEN\n')
]

CLIENTS_LOGIN = [
    ('xxx', 0, 'Open https://github.com/login/device and enter XXXX-XXXX\nConnected to GitHub as xxx\n', '', ['ghu_xxx']),
    ('', 1, '', 'error: Missing required environment variables: GITHUB_APP_CLIENT_ID\n', [])
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

@pytest.mark.parametrize(('client', 'status', 'out', 'err', 'tokens'), CLIENTS_LOGIN)
def test_terminal_command_github_login(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    client: str,
    status: int,
    out: str,
    err: str,
    tokens: list[str]
) -> None:

    key = threadvault.encryption.generate()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_APP_CLIENT_ID', client)
    monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
    monkeypatch.setenv('THREADVAULT_SECRET_KEY', key)

    with respx.mock(assert_all_called = False) as router:

        router.post(threadvault.github.oauth.CODE_URL).respond(200, json = {'device_code': 'xxx1', 'expires_in': 900, 'interval': 0, 'user_code': 'XXXX-XXXX', 'verification_uri': 'https://github.com/login/device'})
        router.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = {'access_token': 'ghu_xxx', 'expires_in': 28800, 'refresh_token': 'ghr_xxx', 'refresh_token_expires_in': 15897600})
        router.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
        assert threadvault.terminal.main(['github-login']) == status

    cipher = threadvault.encryption.SecretCipher(key.encode('ascii'))
    database = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE)))

    try: saved = [json.loads(cipher.decrypt(row['credential_data']))['access_token'] for row in database.connect().execute('SELECT credential_data FROM github')]
    finally: database.close()

    assert capsys.readouterr() == (out, err)
    assert saved == tokens
