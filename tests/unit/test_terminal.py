import builtins
import collections.abc
import datetime
import getpass
import importlib.resources
import json
import os
import pathlib
import sys
import unittest.mock
import urllib.parse
import webbrowser

import cryptography.fernet
import dotenv
import httpx
import pytest
import respx
import slack_bolt
import slack_sdk
import slack_sdk.errors

import threadvault.autostart
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

ENVIRONMENTS_START = [
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'THREADVAULT_OWNER_ID': 'UXXX1', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}, 0, '', ['xapp-xxx']),
    ({'SLACK_APP_TOKEN': '', 'THREADVAULT_OWNER_ID': '', 'GITHUB_APP_CLIENT_ID': '', 'GITHUB_APP_SLUG': ''}, 1, 'error: Missing required environment variables: SLACK_APP_TOKEN, THREADVAULT_OWNER_ID, GITHUB_APP_CLIENT_ID, GITHUB_APP_SLUG\n', [])
]

NOW = datetime.datetime.now(datetime.UTC)

TOKENS_SAVED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx', access_expiry = NOW + datetime.timedelta(hours = 8), refresh_token = 'ghr_xxx', refresh_expiry = NOW + datetime.timedelta(days = 184))

ENVIRONMENT_DOCTOR = {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'THREADVAULT_OWNER_ID': 'UXXX1', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}

DESTINATIONS_CHECKED = [
    ([TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 0, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\nok: destination: xxx/xxx\n', ''),
    ([], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\n', 'error: GitHub is not connected yet\n'),
    ([TOKENS_SAVED], httpx.Response(500), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\n', 'error: GitHub answered 500 to GET /user: \n'),
    ([TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), None, httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\n', 'error: No destination is chosen yet\n'),
    ([TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(404, json = {'message': 'Not Found'}), 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\n', 'error: xxx/xxx does not exist\n'),
    ([TOKENS_SAVED], httpx.Response(200, json = {'login': 'xxx'}), 'xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': False}), 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: git 2.47.0\nok: GitHub: xxx\n', 'error: xxx/xxx is public\n')
]

STAGES_FAILED = [
    ({'SLACK_APP_TOKEN': ''}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], ['2.47.0'], '', 'error: Missing required environment variables: SLACK_APP_TOKEN\n'),
    ({}, slack_sdk.errors.SlackApiError('xxx', 'xxx'), ['2.47.0'], 'ok: settings ({file})\n', 'error: xxx\nThe server responded with: xxx\n'),
    ({}, [{'team_id': 'TXXX', 'url': 'https://xxx.slack.com/'}], threadvault.vault.repository.GitError('xxx'), 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\n', 'error: xxx\n')
]

TOKENS_SETUP = [
    (['xoxb-xxx', 'xapp-xxx'], '', 0, 'ok: Slack: https://xxx.slack.com/\n', '', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx'}),
    (['xapp-xxx', 'xoxb-xxx', 'xoxb-xxx', 'xapp-xxx'], '', 0, 'ok: Slack: https://xxx.slack.com/\n', 'error: SLACK_BOT_TOKEN must be a bot token starting with xoxb-\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx'}),
    (['', '', 'xoxb-xxx', 'xapp-xxx'], '', 0, 'ok: Slack: https://xxx.slack.com/\n', 'error: Missing required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx'}),
    (['', ''], 'SLACK_BOT_TOKEN=xoxb-xxx\nSLACK_APP_TOKEN=xapp-xxx\n', 0, 'ok: Slack: https://xxx.slack.com/\n', '', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx'}),
    ([EOFError()], '', 1, '', '\nerror: Setup was stopped\n', {})
]

APPS_SETUP = [
    (['', 'xxx', 'xxx'], [None], 'https://github.com/settings/apps/new', '', {'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}),
    (['xxx', 'xxx', 'xxx'], [None], 'https://github.com/organizations/xxx/settings/apps/new', '', {'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}),
    (['', 'xxx', 'xxx_xxx', 'xxx', 'xxx'], [None], 'https://github.com/settings/apps/new', 'error: GITHUB_APP_SLUG may only contain lower-case letters, digits and hyphens\n', {'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'}),
    (['', 'xxx', 'xxx', 'xxx', 'xxx'], [threadvault.github.oauth.OAuthError('device_flow_disabled', 'xxx'), None], 'https://github.com/settings/apps/new', 'error: xxx\n', {'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx'})
]

OWNERS_SETUP = [
    (['UXXX2', ''], 'ok: owner: テスト\n', '', {'THREADVAULT_OWNER_ID': 'UXXX2', 'THREADVAULT_ADMIN_IDS': ''}),
    (['xxx', 'UXXX2', ''], 'ok: owner: テスト\n', 'error: THREADVAULT_OWNER_ID must be one Slack user ID\n', {'THREADVAULT_OWNER_ID': 'UXXX2', 'THREADVAULT_ADMIN_IDS': ''}),
    (['UXXX1', 'UXXX2', ''], 'ok: owner: テスト\n', 'error: UXXX1 is not a person in the workspace\n', {'THREADVAULT_OWNER_ID': 'UXXX2', 'THREADVAULT_ADMIN_IDS': ''}),
    (['UXXX2', 'xxx', 'UXXX3,UXXX4'], 'ok: owner: テスト\n', 'error: THREADVAULT_ADMIN_IDS contains invalid Slack user IDs: xxx\n', {'THREADVAULT_OWNER_ID': 'UXXX2', 'THREADVAULT_ADMIN_IDS': 'UXXX3,UXXX4'})
]

DESTINATIONS_SETUP = [
    ([], 'xxx/xxx', 'ok: git 2.47.0\nnext: with the Slack app running, connect GitHub and choose the destination in App Home\n'),
    ([TOKENS_SAVED], None, 'ok: GitHub: xxx\nnext: with the Slack app running, choose the destination in App Home\n'),
    ([TOKENS_SAVED], 'xxx/xxx', 'ok: GitHub: xxx\nok: destination: xxx/xxx\n')
]

PLATFORMS_SETUP = [
    (frozenset({sys.platform}), [''], 'ok: autostart: xxx\n', 1),
    (frozenset({sys.platform}), ['no'], "next: run 'threadvault start' to start the Slack app\n", 0),
    (frozenset[str](), [], "next: run 'threadvault start' to start the Slack app\n", 0)
]

def answer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tokens: collections.abc.Sequence[str | Exception] = ('xoxb-xxx', 'xapp-xxx'),
    apps: collections.abc.Sequence[str | Exception] = ('', 'xxx', 'xxx'),
    codes: collections.abc.Sequence[Exception | None] = (None,),
    owners: collections.abc.Sequence[str | Exception] = ('UXXX2', ''),
    starts: collections.abc.Sequence[str | Exception] = ('no',)
) -> tuple[unittest.mock.Mock, unittest.mock.Mock]:

    browse, request = unittest.mock.Mock(), unittest.mock.Mock(side_effect = codes)

    monkeypatch.setattr(getpass, 'getpass', unittest.mock.Mock(side_effect = tokens))
    monkeypatch.setattr(builtins, 'input', unittest.mock.Mock(side_effect = [*apps, *owners, *starts]))
    monkeypatch.setattr(webbrowser, 'open', browse)
    monkeypatch.setattr(threadvault.github.oauth, 'request', request)

    return browse, request

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

class TestTerminalCommandKey:

    def test_key(
        self,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        assert threadvault.terminal.main(['key']) == 0

        cryptography.fernet.Fernet(capsys.readouterr().out.strip())

class TestTerminalCommandBackup:

    def test_directory(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)

        assert threadvault.terminal.main(['backup', '--out', 'xxx']) == 0
        assert capsys.readouterr() == ('xxx: 0 messages, 0 deleted, 0 withheld, 0 files, 0 failures\ngeneral: 5 messages, 0 deleted, 0 withheld, 0 files, 0 failures\n', '')

    def test_failure(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('SLACK_BOT_TOKEN', '')

        assert threadvault.terminal.main(['backup', '--out', 'xxx']) == 1
        assert capsys.readouterr() == ('', 'error: Missing required environment variables: SLACK_BOT_TOKEN\n')

    def test_repository(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('GITHUB_APP_CLIENT_ID', 'xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setenv('THREADVAULT_SECRET_KEY', threadvault.encryption.generate())
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)

        assert threadvault.terminal.main(['backup', '--repo', 'xxx/xxx']) == 1
        assert capsys.readouterr() == ('', 'error: GitHub is not connected yet\n')

    def test_lock(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        directory = pathlib.Path(os.path.join(tmp_path, threadvault.backup.runner.VAULTS_DIRECTORY, 'xxx', 'xxx'))

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('GITHUB_APP_CLIENT_ID', 'xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setenv('THREADVAULT_SECRET_KEY', threadvault.encryption.generate())
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)

        with threadvault.backup.runner.hold(directory): assert threadvault.terminal.main(['backup', '--repo', 'xxx/xxx']) == 1
        assert capsys.readouterr() == ('', f'error: Another backup is already writing {directory}\n')

    def test_configuration(
        self,
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

        assert threadvault.terminal.main(['backup', '--out', 'xxx']) == 0
        assert capsys.readouterr() == ('general: 5 messages, 0 deleted, 0 withheld, 0 files, 0 failures\n', '')

class TestTerminalCommandConnect:

    def test_connection(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        key = threadvault.encryption.generate()

        monkeypatch.setenv('GITHUB_APP_CLIENT_ID', 'xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setenv('THREADVAULT_SECRET_KEY', key)

        with respx.mock:

            respx.post(threadvault.github.oauth.CODE_URL).respond(200, json = {'device_code': 'xxx1', 'expires_in': 900, 'interval': 0, 'user_code': 'XXXX-XXXX', 'verification_uri': 'https://github.com/login/device'})
            respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = {'access_token': 'ghu_xxx', 'expires_in': 28800, 'refresh_token': 'ghr_xxx', 'refresh_token_expires_in': 15897600})
            respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})

            assert threadvault.terminal.main(['connect']) == 0

        cipher = threadvault.encryption.SecretCipher(key.encode('ascii'))
        database = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE)))

        try: saved = [json.loads(cipher.decrypt(row['credential_data']))['access_token'] for row in database.connect().execute('SELECT credential_data FROM github')]
        finally: database.close()

        assert capsys.readouterr() == ('Open https://github.com/login/device and enter XXXX-XXXX\nConnected to GitHub as xxx\n', '')
        assert saved == ['ghu_xxx']

    def test_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        monkeypatch.setenv('GITHUB_APP_CLIENT_ID', '')

        assert threadvault.terminal.main(['connect']) == 1
        assert capsys.readouterr() == ('', 'error: Missing required environment variables: GITHUB_APP_CLIENT_ID\n')

class TestTerminalCommandStart:

    @pytest.mark.parametrize(('environment', 'status', 'err', 'started'), ENVIRONMENTS_START)
    def test_environment(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        environment: dict[str, str],
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

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.slack.application, 'start', start)

        for name, value in environment.items(): monkeypatch.setenv(name, value)

        assert threadvault.terminal.main(['start']) == status
        assert capsys.readouterr() == ('', err)
        assert tokens == started

    def test_lock(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('SLACK_APP_TOKEN', 'xapp-xxx')
        monkeypatch.setenv('THREADVAULT_OWNER_ID', 'UXXX1')
        monkeypatch.setenv('GITHUB_APP_CLIENT_ID', 'xxx')
        monkeypatch.setenv('GITHUB_APP_SLUG', 'xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.slack.application, 'start', unittest.mock.Mock())

        with threadvault.slack.application.lock(tmp_path): assert threadvault.terminal.main(['start']) == 1
        assert capsys.readouterr() == ('', f'error: {threadvault.product.NAME} is already running with the data directory {tmp_path}\n')

    def test_log(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        log = pathlib.Path(os.path.join(tmp_path, 'xxx', 'xxx.log'))

        def connect(
            token: str
        ) -> slack_sdk.web.WebClient:

            sys.stdout.write(f'{token}\n')

            return slack

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('THREADVAULT_OWNER_ID', 'UXXX1')
        monkeypatch.setenv('GITHUB_APP_CLIENT_ID', 'xxx')
        monkeypatch.setenv('GITHUB_APP_SLUG', 'xxx')
        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.slack.application, 'start', unittest.mock.Mock(side_effect = KeyboardInterrupt))
        monkeypatch.setenv('SLACK_APP_TOKEN', '')

        assert threadvault.terminal.main(['start', '--log', str(log)]) == 1

        monkeypatch.setenv('SLACK_APP_TOKEN', 'xapp-xxx')

        assert threadvault.terminal.main(['start', '--log', str(log)]) == 0
        assert capsys.readouterr() == ('', '')
        assert log.read_text(encoding = 'utf-8') == 'error: Missing required environment variables: SLACK_APP_TOKEN\nxoxb-xxx\n'

class TestTerminalCommandManifest:

    def test_manifest(
        self,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        assert threadvault.terminal.main(['manifest']) == 0

        manifest = json.loads(capsys.readouterr().out)

        assert manifest['oauth_config']['scopes']['bot'] == ['channels:history', 'channels:join', 'channels:read', 'chat:write', 'files:read', 'groups:history', 'groups:read', 'reactions:read', 'users:read']
        assert manifest['features']['app_home']['home_tab_enabled']
        assert manifest['features']['app_home']['messages_tab_enabled']
        assert manifest['features']['app_home']['messages_tab_read_only_enabled']
        assert manifest['settings']['event_subscriptions']['bot_events'] == ['app_home_opened', 'message.channels', 'message.groups']
        assert manifest['settings']['interactivity']['is_enabled']
        assert manifest['settings']['socket_mode_enabled']

class TestTerminalCommandDoctor:

    @pytest.mark.parametrize(('tokens', 'user', 'repository', 'found', 'status', 'out', 'err'), DESTINATIONS_CHECKED)
    def test_destination(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
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

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setenv('THREADVAULT_SECRET_KEY', key)
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.vault.repository, 'verify', unittest.mock.Mock(return_value = '2.47.0'))

        for name, value in ENVIRONMENT_DOCTOR.items(): monkeypatch.setenv(name, value)

        with respx.mock(assert_all_called = False) as router:

            router.get(f'{threadvault.github.rest.API_URL}/user').mock(return_value = user)
            router.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').mock(return_value = found)

            assert threadvault.terminal.main(['doctor']) == status

        assert capsys.readouterr() == (out.format(file = configuration), err)

    @pytest.mark.parametrize(('environment', 'identity', 'version', 'out', 'err'), STAGES_FAILED)
    def test_stage(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        environment: dict[str, str],
        identity: list[dict[str, str]] | Exception,
        version: list[str] | Exception,
        out: str,
        err: str
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'auth_test', unittest.mock.Mock(side_effect = identity))
        monkeypatch.setattr(threadvault.vault.repository, 'verify', unittest.mock.Mock(side_effect = version))

        for name, value in (ENVIRONMENT_DOCTOR | environment).items(): monkeypatch.setenv(name, value)

        assert threadvault.terminal.main(['doctor']) == 1
        assert capsys.readouterr() == (out.format(file = configuration), err)

class TestTerminalCommandSetup:

    @pytest.mark.parametrize(('tokens', 'saved', 'status', 'out', 'err', 'written'), TOKENS_SETUP)
    def test_slack(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        tokens: list[str | Exception],
        saved: str,
        status: int,
        out: str,
        err: str,
        written: dict[str, str]
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        manifest = json.loads(importlib.resources.files('threadvault.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))

        if saved:

            configuration.parent.mkdir()
            configuration.write_text(saved, encoding = 'utf-8')

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        browse, _ = answer(monkeypatch, tokens = tokens)

        assert threadvault.terminal.main(['setup']) == status

        captured = capsys.readouterr()
        url: str = browse.call_args_list[0].args[0]

        assert out in captured.out
        assert captured.err == err
        assert json.loads(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['manifest_json'][0]) == manifest
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name.startswith('SLACK_')} == written

    def test_refusal(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'apps_connections_open', unittest.mock.Mock(side_effect = [slack_sdk.errors.SlackApiError('xxx', 'xxx'), {'url': 'wss://xxx'}]))
        answer(monkeypatch, tokens = ['xoxb-xxx', 'xapp-xxx1', 'xoxb-xxx', 'xapp-xxx2'])

        assert threadvault.terminal.main(['setup']) == 0
        assert capsys.readouterr().err == 'error: xxx\nThe server responded with: xxx\n'
        assert dotenv.dotenv_values(configuration)['SLACK_APP_TOKEN'] == 'xapp-xxx2'

    @pytest.mark.parametrize(('apps', 'codes', 'page', 'err', 'written'), APPS_SETUP)
    def test_github(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        apps: list[str],
        codes: list[Exception | None],
        page: str,
        err: str,
        written: dict[str, str]
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        browse, request = answer(monkeypatch, apps = apps, codes = codes)

        assert threadvault.terminal.main(['setup']) == 0

        captured = capsys.readouterr()
        address: str = browse.call_args_list[1].args[0]
        url = urllib.parse.urlsplit(address)

        assert captured.err == err
        assert 'ok: GitHub App: xxx\n' in captured.out
        assert f'{url.scheme}://{url.netloc}{url.path}' == page
        assert urllib.parse.parse_qs(url.query) == {'name': ['ThreadVault for xxx'], 'url': ['https://xxx.slack.com/'], 'public': ['false'], 'webhook_active': ['false'], 'contents': ['write'], 'administration': ['write'], 'metadata': ['read']}
        assert request.call_args_list == [unittest.mock.call('xxx')] * len(codes)
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name.startswith('GITHUB_APP_')} == written

    @pytest.mark.parametrize(('owners', 'out', 'err', 'written'), OWNERS_SETUP)
    def test_owner(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        owners: list[str],
        out: str,
        err: str,
        written: dict[str, str]
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        answer(monkeypatch, owners = owners)

        assert threadvault.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert out in captured.out
        assert captured.err == err
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name.startswith('THREADVAULT_')} == written

    def test_bot(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'users_info', unittest.mock.Mock(side_effect = [{'user': {'id': 'UXXX9', 'is_bot': True}}, {'user': {'id': 'UXXX2', 'name': 'xxx'}}]))
        answer(monkeypatch, owners = ['UXXX9', 'UXXX2', ''])

        assert threadvault.terminal.main(['setup']) == 0
        assert capsys.readouterr().err == 'error: UXXX9 is not a person in the workspace\n'

    @pytest.mark.parametrize(('tokens', 'repository', 'out'), DESTINATIONS_SETUP)
    def test_check(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        tokens: list[threadvault.github.oauth.Tokens],
        repository: str | None,
        out: str
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

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setenv('THREADVAULT_SECRET_KEY', key)
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.vault.repository, 'verify', unittest.mock.Mock(return_value = '2.47.0'))
        answer(monkeypatch)

        with respx.mock(assert_all_called = False) as router:

            router.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
            router.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').respond(200, json = {'full_name': 'xxx/xxx', 'private': True})

            assert threadvault.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert out in captured.out
        assert not captured.err

    @pytest.mark.parametrize(('platforms', 'starts', 'out', 'registrations'), PLATFORMS_SETUP)
    def test_autostart(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        platforms: frozenset[str],
        starts: list[str],
        out: str,
        registrations: int
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        register = unittest.mock.Mock(return_value = 'xxx')

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.vault.repository, 'verify', unittest.mock.Mock(return_value = '2.47.0'))
        monkeypatch.setattr(threadvault.autostart, 'register', register)
        monkeypatch.setattr(threadvault.autostart, 'PLATFORMS', platforms)
        answer(monkeypatch, starts = starts)

        assert threadvault.terminal.main(['setup']) == 0
        assert capsys.readouterr().out.endswith(out)
        assert register.call_args_list == [unittest.mock.call(pathlib.Path(os.path.join(tmp_path, 'start.log')))] * registrations

    def test_failure(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        register = unittest.mock.Mock()

        monkeypatch.setenv('THREADVAULT_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(threadvault.slack.api, 'connect', connect)
        monkeypatch.setattr(threadvault.vault.repository, 'verify', unittest.mock.Mock(side_effect = threadvault.vault.repository.GitError('xxx')))
        monkeypatch.setattr(threadvault.autostart, 'register', register)
        monkeypatch.setattr(threadvault.autostart, 'PLATFORMS', frozenset({sys.platform}))
        answer(monkeypatch, starts = [''])

        assert threadvault.terminal.main(['setup']) == 1
        assert capsys.readouterr().err == 'error: xxx\n'
        assert not register.called
