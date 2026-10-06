import collections.abc
import datetime
import os
import pathlib
import threading
import typing

import pytest
import respx
import slack_bolt
import slack_sdk
import slack_sdk.errors

import threadvault.configuration
import threadvault.customisation
import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.token
import threadvault.slack.handler
import threadvault.slack.permission
import threadvault.slack.view
import threadvault.storage

NOW = datetime.datetime(2026, 10, 5, 0, 0, tzinfo = datetime.UTC)

CODE = threadvault.github.oauth.Code(device_code = 'xxx', user_code = 'XXXX-XXXX', verification_uri = 'https://github.com/login/device', interval = 0)
TOKENS_SAVED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx', access_expiry = NOW + datetime.timedelta(hours = 8), refresh_token = 'ghr_xxx', refresh_expiry = NOW + datetime.timedelta(days = 184))

CODE_ISSUED = {'device_code': 'xxx', 'expires_in': 900, 'interval': 0, 'user_code': 'XXXX-XXXX', 'verification_uri': 'https://github.com/login/device'}
TOKENS_ISSUED = {'access_token': 'ghu_xxx', 'expires_in': 28800, 'refresh_token': 'ghr_xxx', 'refresh_token_expires_in': 15897600}

TABS_OPENED = [('home', 1), ('messages', 0)]
VIEWERS_HOME = [('UXXX1', 'owner'), ('UXXX2', 'admin'), ('UXXX3', 'member')]

CONNECTIONS_FAILED = [
    ({'error': 'device_flow_disabled', 'error_description': 'xxx'}, TOKENS_ISSUED, 'device_flow_disabled'),
    (CODE_ISSUED, {'error': 'access_denied', 'error_description': 'xxx'}, 'access_denied'),
    (CODE_ISSUED, {'error': 'expired_token', 'error_description': 'xxx'}, 'expired_token')
]

@pytest.fixture
def application(
    monkeypatch: pytest.MonkeyPatch,
    slack: slack_sdk.web.WebClient,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> slack_bolt.App:

    def detach(
        function: collections.abc.Callable[[], None]
    ) -> None:

        function()

    application = slack_bolt.App(client = slack, process_before_response = True)
    monkeypatch.setattr(threadvault.slack.handler, 'detach', detach)
    threadvault.slack.handler.register(application, threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX2', 'GITHUB_APP_CLIENT_ID': 'xxx', 'THREADVAULT_LANGUAGE_DISPLAY': 'ja'}), database, manager)

    return application

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

@pytest.fixture
def manager(
    database: threadvault.storage.Database
) -> threadvault.github.token.TokenManager:

    return threadvault.github.token.TokenManager(database, threadvault.encryption.SecretCipher(threadvault.encryption.generate().encode('ascii')), 'xxx')

def home(
    application: slack_bolt.App,
    user: str,
    tab: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'event_callback', 'team_id': 'TXXX', 'event': {'type': 'app_home_opened', 'user': user, 'channel': 'DXXX', 'tab': tab}}, mode = 'socket_mode'))

def press(
    application: slack_bolt.App,
    user: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'trigger_id': 'xxx', 'actions': [{'type': 'button', 'action_id': threadvault.slack.view.CONNECTION_ACTION}]}, mode = 'socket_mode'))

def calls(
    workspace: dict[str, typing.Any],
    method: str
) -> list[dict[str, typing.Any]]:

    return [arguments for name, arguments in workspace['calls'] if name == method]

@pytest.mark.parametrize(('user', 'role'), VIEWERS_HOME)
def test_handler_home_publication(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager,
    user: str,
    role: threadvault.slack.permission.Role
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx'), update_user = 'UXXX1')
    manager.save(TOKENS_SAVED)

    assert home(application, user, 'home').status == 200
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': threadvault.slack.view.home(connected = True, destination = 'xxx/xxx', role = role, language = 'ja')}]

def test_handler_home_locale(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['locale'] = 'en-GB'

    assert home(application, 'UXXX1', 'home').status == 200
    assert calls(workspace, 'users.info') == [{'user': 'UXXX1', 'include_locale': True}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(connected = False, destination = None, role = 'owner', language = 'en')}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(connected = False, destination = None, role = 'owner', language = 'ja')}] * count

def test_handler_github_connection(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    with respx.mock:

        respx.post(threadvault.github.oauth.CODE_URL).respond(200, json = CODE_ISSUED)
        respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = TOKENS_ISSUED)

        assert press(application, 'UXXX1').status == 200

    assert manager.acquire(datetime.datetime.now(datetime.UTC)) == 'ghu_xxx'
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.connect(code = None, language = 'ja')}]
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.connect(code = CODE, language = 'ja')}, {'view_id': 'VXXX', 'view': threadvault.slack.view.respond(error = None, language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(connected = True, destination = None, role = 'owner', language = 'ja')}]

@pytest.mark.parametrize(('code', 'tokens', 'reason'), CONNECTIONS_FAILED)
def test_handler_github_failure(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager,
    code: dict[str, typing.Any],
    tokens: dict[str, typing.Any],
    reason: str
) -> None:

    with respx.mock(assert_all_called = False) as router:

        router.post(threadvault.github.oauth.CODE_URL).respond(200, json = code)
        router.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = tokens)

        assert press(application, 'UXXX1').status == 200

    assert not manager.connected()
    assert calls(workspace, 'views.update')[-1] == {'view_id': 'VXXX', 'view': threadvault.slack.view.respond(error = threadvault.github.oauth.OAuthError(reason, 'xxx'), language = 'ja')}
    assert calls(workspace, 'views.publish') == []

def test_handler_github_closure(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    slack: slack_sdk.web.WebClient,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    def update(
        **_: object
    ) -> None:

        raise slack_sdk.errors.SlackApiError('xxx', {'ok': False, 'error': 'not_found'})

    monkeypatch.setattr(slack, 'views_update', update)

    with respx.mock:

        respx.post(threadvault.github.oauth.CODE_URL).respond(200, json = CODE_ISSUED)
        respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = TOKENS_ISSUED)

        assert press(application, 'UXXX1').status == 200

    assert manager.connected()
    assert len(calls(workspace, 'views.publish')) == 1

def test_handler_github_permission(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    assert press(application, 'UXXX3').status == 200
    assert calls(workspace, 'views.open') == []

def test_handler_thread_detachment() -> None:

    threads: list[threading.Thread] = []
    started = threading.Event()

    def run() -> None:

        threads.append(threading.current_thread())
        started.set()

    threadvault.slack.handler.detach(run)

    assert started.wait(5)
    assert threads[0] is not threading.current_thread()
    assert threads[0].daemon
