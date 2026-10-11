import collections.abc
import contextlib
import datetime
import json
import os
import pathlib
import unittest.mock

import cryptography.fernet
import httpx
import pytest
import respx
import slack_bolt
import slack_sdk
import slack_sdk.errors

import threadvault.backup.runner
import threadvault.customisation
import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.github.token
import threadvault.product
import threadvault.slack.api
import threadvault.slack.application
import threadvault.storage
import threadvault.terminal
import threadvault.vault.repository

TOKENS_BACKUP = [
    ('xoxb-xxx', ['--out', 'xxx'], contextlib.nullcontext, 0, 'xxx: 0 messages, 0 deleted, 0 withheld, 0 files, 0 failures\ngeneral: 5 messages, 0 deleted, 0 withheld, 0 files, 0 failures\n', ''),
    ('', ['--out', 'xxx'], contextlib.nullcontext, 1, '', 'error: Missing required environment variables: SLACK_BOT_TOKEN\n'),
    ('xoxb-xxx', ['--repo', 'xxx/xxx'], contextlib.nullcontext, 1, '', 'error: GitHub is not connected yet\n'),
    ('xoxb-xxx', ['--repo', 'xxx/xxx'], threadvault.backup.runner.hold, 1, '', 'error: Another backup is already writing {directory}\n')
]

CLIENTS_LOGIN = [
    ('xxx', 0, 'Open https://github.com/login/device and enter XXXX-XXXX\nConnected to GitHub as xxx\n', '', ['ghu_xxx']),
    ('', 1, '', 'error: Missing required environment variables: GITHUB_APP_CLIENT_ID\n', [])
]

ENVIRONMENTS_SERVE = [
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'THREADVAULT_OWNER_ID': 'UXXX1', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}, contextlib.nullcontext, 0, '', ['xapp-xxx']),
    ({'SLACK_APP_TOKEN': '', 'THREADVAULT_OWNER_ID': '', 'GITHUB_APP_CLIENT_ID': '', 'GITHUB_APP_SLUG': ''}, contextlib.nullcontext, 1, 'error: Missing required environment variables: SLACK_APP_TOKEN, THREADVAULT_OWNER_ID, GITHUB_APP_CLIENT_ID, GITHUB_APP_SLUG\n', []),
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'THREADVAULT_OWNER_ID': 'UXXX1', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}, threadvault.slack.application.lock, 1, 'error: {product} is already running with the data directory {directory}\n', [])
]

NOW = datetime.datetime.now(datetime.UTC)

TOKENS_SAVED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx', access_expiry = NOW + datetime.timedelta(hours = 8), refresh_token = 'ghr_xxx', refresh_expiry = NOW + datetime.timedelta(days = 184))

ENVIRONMENT_DOCTOR = {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'THREADVAULT_OWNER_ID': 'UXXX1', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}

STAGES_CHECKED = [
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 0, 'ok: settings\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\nok: destination: xxx/xxx\n', ''),
    ({'SLACK_APP_TOKEN': ''}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, '', 'error: Missing required environment variables: SLACK_APP_TOKEN\n'),
    ({}, slack_sdk.errors.SlackApiError('xxx', 'xxx'), ['2.47.0'], [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings\n', 'error: xxx\nThe server responded with: xxx\n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], threadvault.vault.repository.GitError('xxx'), [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings\nok: Slack: https://xxx.slack.com/\n', 'error: xxx\n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\n', 'error: GitHub is not connected yet\n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [TOKENS_SAVED], httpx.Response(500), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\n', 'error: GitHub answered 500 to GET /user: \n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), None, httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\n', 'error: No destination is chosen yet\n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(404, json = {'message': 'Not Found'}), 1, 'ok: settings\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\n', 'error: xxx/xxx does not exist\n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], [TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': False}), 1, 'ok: settings\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\n', 'error: xxx/xxx is public\n')
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

@pytest.mark.parametrize(('token', 'arguments', 'holder', 'status', 'out', 'err'), TOKENS_BACKUP)
def test_terminal_command_backup_now(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slack: slack_sdk.web.WebClient,
    token: str,
    arguments: list[str],
    holder: collections.abc.Callable[[pathlib.Path], contextlib.AbstractContextManager[object]],
    status: int,
    out: str,
    err: str
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, threadvault.backup.runner.VAULTS_DIRECTORY, 'xxx', 'xxx'))

    def connect(
        _: str
    ) -> slack_sdk.web.WebClient:

        return slack

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', token)
    monkeypatch.setenv('GITHUB_APP_CLIENT_ID', 'xxx')
    monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
    monkeypatch.setenv('THREADVAULT_SECRET_KEY', threadvault.encryption.generate())
    monkeypatch.setattr(threadvault.slack.api, 'connect', connect)

    with holder(directory): assert threadvault.terminal.main(['backup-now', *arguments]) == status
    assert capsys.readouterr() == (out, err.format(directory = directory))

def test_terminal_command_backup_configuration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slack: slack_sdk.web.WebClient
) -> None:

    def connect(
        _: str
    ) -> slack_sdk.web.WebClient:

        return slack

    database = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE)))

    try: threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(channel_mode = 'selected', channels_selected = ('CXXX1',)), update_user = 'UXXX1')
    finally: database.close()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
    monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
    monkeypatch.setattr(threadvault.slack.api, 'connect', connect)

    assert threadvault.terminal.main(['backup-now', '--out', 'xxx']) == 0
    assert capsys.readouterr() == ('general: 5 messages, 0 deleted, 0 withheld, 0 files, 0 failures\n', '')

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

@pytest.mark.parametrize(('environment', 'holder', 'status', 'err', 'started'), ENVIRONMENTS_SERVE)
def test_terminal_command_slack_serve(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slack: slack_sdk.web.WebClient,
    environment: dict[str, str],
    holder: collections.abc.Callable[[pathlib.Path], contextlib.AbstractContextManager[object]],
    status: int,
    err: str,
    started: list[str]
) -> None:

    tokens = []

    def connect(
        _: str
    ) -> slack_sdk.web.WebClient:

        return slack

    def start(
        _: slack_bolt.App,
        token: str,
        schedule: collections.abc.Callable[[str, datetime.datetime], None]
    ) -> None:

        tokens.append(token)
        schedule('TXXX', datetime.datetime.now(datetime.UTC))

        raise KeyboardInterrupt

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
    monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
    monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
    monkeypatch.setattr(threadvault.slack.application, 'start', start)

    for name, value in environment.items(): monkeypatch.setenv(name, value)

    with holder(tmp_path): assert threadvault.terminal.main(['slack-serve']) == status
    assert capsys.readouterr() == ('', err.format(product = threadvault.product.NAME, directory = tmp_path))
    assert tokens == started

def test_terminal_command_print_manifest(
    capsys: pytest.CaptureFixture[str]
) -> None:

    assert threadvault.terminal.main(['print-manifest']) == 0

    manifest = json.loads(capsys.readouterr().out)

    assert manifest['oauth_config']['scopes']['bot'] == ['channels:history', 'channels:join', 'channels:read', 'chat:write', 'files:read', 'groups:history', 'groups:read', 'reactions:read', 'users:read']
    assert manifest['features']['app_home']['home_tab_enabled']
    assert manifest['features']['app_home']['messages_tab_enabled']
    assert manifest['features']['app_home']['messages_tab_read_only_enabled']
    assert manifest['settings']['event_subscriptions']['bot_events'] == ['app_home_opened', 'message.channels', 'message.groups']
    assert manifest['settings']['interactivity']['is_enabled']
    assert manifest['settings']['socket_mode_enabled']

@pytest.mark.parametrize(('environment', 'identity', 'version', 'tokens', 'user', 'repository', 'found', 'status', 'out', 'err'), STAGES_CHECKED)
def test_terminal_command_doctor(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slack: slack_sdk.web.WebClient,
    environment: dict[str, str],
    identity: list[dict[str, str]] | Exception,
    version: list[str] | Exception,
    tokens: list[threadvault.github.oauth.Tokens],
    user: httpx.Response,
    repository: str | None,
    found: httpx.Response,
    status: int,
    out: str,
    err: str
) -> None:

    def connect(
        _: str
    ) -> slack_sdk.web.WebClient:

        return slack

    key = threadvault.encryption.generate()
    database = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE)))

    try:

        threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = repository), update_user = 'UXXX1')

        for pair in tokens: threadvault.github.token.TokenManager(database, threadvault.encryption.SecretCipher(key.encode('ascii')), 'xxx').save(pair)

    finally:

        database.close()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
    monkeypatch.setenv('THREADVAULT_SECRET_KEY', key)
    monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
    monkeypatch.setattr(slack, 'auth_test', unittest.mock.Mock(side_effect = identity))
    monkeypatch.setattr(threadvault.vault.repository, 'verify', unittest.mock.Mock(side_effect = version))

    for name, value in (ENVIRONMENT_DOCTOR | environment).items(): monkeypatch.setenv(name, value)

    with respx.mock(assert_all_called = False) as router:

        router.get(f'{threadvault.github.rest.API_URL}/user').mock(return_value = user)
        router.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').mock(return_value = found)

        assert threadvault.terminal.main(['doctor']) == status

    assert capsys.readouterr() == (out, err)
