import collections.abc
import datetime
import json
import os
import pathlib
import threading
import typing
import unittest.mock

import httpx
import pytest
import respx
import slack_bolt
import slack_sdk
import slack_sdk.errors

import threadvault.backup.runner
import threadvault.configuration
import threadvault.customisation
import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.github.token
import threadvault.localisation
import threadvault.product
import threadvault.slack.handler
import threadvault.slack.permission
import threadvault.slack.view
import threadvault.storage
import threadvault.worker

NOW = datetime.datetime.now(datetime.UTC)

CODE = threadvault.github.oauth.Code(device_code = 'xxx', user_code = 'XXXX-XXXX', verification_uri = 'https://github.com/login/device', interval = 0)
TOKENS_SAVED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx', access_expiry = NOW + datetime.timedelta(hours = 8), refresh_token = 'ghr_xxx', refresh_expiry = NOW + datetime.timedelta(days = 184))
TOKENS_EXPIRED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx', access_expiry = NOW - datetime.timedelta(days = 184), refresh_token = 'ghr_xxx', refresh_expiry = NOW - datetime.timedelta(seconds = 1))

CODE_ISSUED = {'device_code': 'xxx', 'expires_in': 900, 'interval': 0, 'user_code': 'XXXX-XXXX', 'verification_uri': 'https://github.com/login/device'}
TOKENS_ISSUED = {'access_token': 'ghu_xxx', 'expires_in': 28800, 'refresh_token': 'ghr_xxx', 'refresh_token_expires_in': 15897600}
REPOSITORIES_RESPONDED = {'total_count': 2, 'repositories': [{'full_name': 'xxx/xxx1', 'private': True}, {'full_name': 'xxx/xxx2', 'private': True}]}
INSTALLATIONS_RESPONDED = {'total_count': 1, 'installations': [{'id': 1}]}

TABS_OPENED = [('home', 1), ('messages', 0)]
VIEWERS_HOME = [('UXXX1', 'owner'), ('UXXX2', 'admin'), ('UXXX3', 'member')]

CONNECTIONS_PERMITTED = [
    ('UXXX2', ('UXXX2',), 1),
    ('UXXX2', (), 0),
    ('UXXX3', ('UXXX3',), 0)
]

CONNECTIONS_FAILED = [
    ({'error': 'device_flow_disabled', 'error_description': 'xxx'}, TOKENS_ISSUED, 'device_flow_disabled'),
    (CODE_ISSUED, {'error': 'access_denied', 'error_description': 'xxx'}, 'access_denied'),
    (CODE_ISSUED, {'error': 'expired_token', 'error_description': 'xxx'}, 'expired_token')
]

CONNECTIONS_EXPIRED = [
    (TOKENS_EXPIRED, httpx.Response(200, json = INSTALLATIONS_RESPONDED)),
    (TOKENS_SAVED, httpx.Response(401, json = {'message': 'Bad credentials'}))
]

ERRORS_BACKUP = [
    threadvault.backup.runner.VaultError('xxx'),
    threadvault.backup.runner.LockError('xxx')
]

DESTINATIONS_REFUSED = [
    ('xxx/xxx', httpx.Response(404, json = {'message': 'Not Found'}), 'absence', ''),
    ('xxx/xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': False}), 'publicity', ''),
    ('xxx/xxx', httpx.Response(500, text = 'xxx'), 'failure', 'GitHub answered 500 to GET /repos/xxx/xxx: xxx'),
    ('xxx', httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True}), 'failure', 'Repository must look like owner/name')
]

CREATIONS_FAILED = [
    ('xxx', httpx.Response(422, text = 'xxx'), 'GitHub answered 422 to POST /user/repos: xxx'),
    ('xxx xxx', httpx.Response(201, json = {'full_name': 'xxx/xxx xxx'}), 'Repository must look like owner/name')
]

INSTALLATIONS_LISTED = [
    (httpx.Response(200, json = INSTALLATIONS_RESPONDED), 'connected'),
    (httpx.Response(200, json = {'total_count': 0, 'installations': []}), 'uninstalled'),
    (httpx.Response(500), 'connected')
]

TRANSFERS_ALLOWED = [
    ((), ('UXXX1',)),
    (('UXXX2', 'UXXX3'), ('UXXX1', 'UXXX3'))
]

SUCCESSORS_INVALID = ['UXXX1', 'UXXX3']

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
    threadvault.slack.handler.register(application, threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX2', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx', 'THREADVAULT_LANGUAGE_DISPLAY': 'ja'}), database, manager)

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
    user: str,
    action: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'trigger_id': 'xxx', 'actions': [{'type': 'button', 'action_id': action}]}, mode = 'socket_mode'))

def submit(
    application: slack_bolt.App,
    user: str,
    view: dict[str, typing.Any]
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'view_submission', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'view': {'id': 'VXXX', 'type': 'modal', 'state': {'values': {}}} | view}, mode = 'socket_mode'))

def suggest(
    application: slack_bolt.App,
    user: str,
    value: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'block_suggestion', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'action_id': threadvault.slack.view.REPOSITORY_ACTION, 'block_id': threadvault.slack.view.REPOSITORY_ACTION, 'value': value}, mode = 'socket_mode'))

def checked(
    users: list[str]
) -> dict[str, typing.Any]:

    return {'callback_id': threadvault.slack.view.PERMISSIONS_CALLBACK, 'state': {'values': {f'{threadvault.slack.view.ADMINS_INPUT}0': {threadvault.slack.view.ADMINS_INPUT: {'type': 'checkboxes', 'selected_options': [{'value': user} for user in users]}}}}}

def selected(
    user: str
) -> dict[str, typing.Any]:

    return {'callback_id': threadvault.slack.view.TRANSFER_CALLBACK, 'state': {'values': {threadvault.slack.view.SUCCESSOR_INPUT: {threadvault.slack.view.SUCCESSOR_INPUT: {'type': 'users_select', 'selected_user': user}}}}}

def chosen(
    repository: str
) -> dict[str, typing.Any]:

    return {'callback_id': threadvault.slack.view.DESTINATION_CALLBACK, 'state': {'values': {threadvault.slack.view.REPOSITORY_ACTION: {threadvault.slack.view.REPOSITORY_ACTION: {'type': 'external_select', 'selected_option': {'text': {'type': 'plain_text', 'text': repository}, 'value': repository}}}}}}

def named(
    account: str,
    name: str
) -> dict[str, typing.Any]:

    return {'callback_id': threadvault.slack.view.CREATION_CALLBACK, 'state': {'values': {threadvault.slack.view.ACCOUNT_INPUT: {threadvault.slack.view.ACCOUNT_INPUT: {'type': 'static_select', 'selected_option': {'text': {'type': 'plain_text', 'text': account}, 'value': account}}}, threadvault.slack.view.NAME_INPUT: {threadvault.slack.view.NAME_INPUT: {'type': 'plain_text_input', 'value': name}}}}}

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

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert home(application, user, 'home').status == 200

    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx', running = False, role = role, slug = 'xxx', language = 'ja')}]

def test_handler_home_locale(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['locale'] = 'en-GB'

    assert home(application, 'UXXX1', 'home').status == 200
    assert calls(workspace, 'users.info') == [{'user': 'UXXX1', 'include_locale': True}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, role = 'owner', slug = 'xxx', language = 'en')}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, role = 'owner', slug = 'xxx', language = 'ja')}] * count

def test_handler_github_connection(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX2')['locale'] = 'en-GB'

    with respx.mock:

        respx.post(threadvault.github.oauth.CODE_URL).respond(200, json = CODE_ISSUED)
        respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = TOKENS_ISSUED)
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert press(application, 'UXXX1', threadvault.slack.view.CONNECTION_ACTION).status == 200

    assert manager.acquire(datetime.datetime.now(datetime.UTC)) == 'ghu_xxx'
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.connect(code = None, language = 'ja')}]
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.connect(code = CODE, language = 'ja')}, {'view_id': 'VXXX', 'view': threadvault.slack.view.respond(error = None, language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = None, running = False, role = 'owner', slug = 'xxx', language = 'ja')}]
    assert calls(workspace, 'chat.postMessage') == [{'channel': 'UXXX1', 'text': threadvault.localisation.translate('notice.connection', 'ja', user = 'UXXX1')}, {'channel': 'UXXX2', 'text': threadvault.localisation.translate('notice.connection', 'en', user = 'UXXX1')}]

def test_handler_github_disconnection(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    assert press(application, 'UXXX1', threadvault.slack.view.DISCONNECTION_ACTION).status == 200
    assert not manager.connected()
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, role = 'owner', slug = 'xxx', language = 'ja')}]
    assert calls(workspace, 'chat.postMessage') == [{'channel': admin, 'text': threadvault.localisation.translate('notice.disconnection', 'ja', user = 'UXXX1')} for admin in ('UXXX1', 'UXXX2')]

@pytest.mark.parametrize(('response', 'github'), INSTALLATIONS_LISTED)
def test_handler_github_installation(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager,
    response: httpx.Response,
    github: threadvault.slack.view.GitHubState
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').mock(return_value = response)

        assert home(application, 'UXXX1', 'home').status == 200

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = github, destination = None, running = False, role = 'owner', slug = 'xxx', language = 'ja')}]

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

        assert press(application, 'UXXX1', threadvault.slack.view.CONNECTION_ACTION).status == 200

    assert not manager.connected()
    assert calls(workspace, 'views.update')[-1] == {'view_id': 'VXXX', 'view': threadvault.slack.view.respond(error = threadvault.github.oauth.OAuthError(reason, 'xxx'), language = 'ja')}
    assert calls(workspace, 'views.publish') == []
    assert calls(workspace, 'chat.postMessage') == []

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
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert press(application, 'UXXX1', threadvault.slack.view.CONNECTION_ACTION).status == 200

    assert manager.connected()
    assert len(calls(workspace, 'views.publish')) == 1

@pytest.mark.parametrize(('tokens', 'response'), CONNECTIONS_EXPIRED)
def test_handler_github_expiry(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager,
    tokens: threadvault.github.oauth.Tokens,
    response: httpx.Response
) -> None:

    manager.save(tokens)

    with respx.mock(assert_all_called = False) as router:

        router.get(f'{threadvault.github.rest.API_URL}/user/installations').mock(return_value = response)

        assert home(application, 'UXXX1', 'home').status == 200

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'expired', destination = None, running = False, role = 'owner', slug = 'xxx', language = 'ja')}]

@pytest.mark.parametrize(('user', 'allowed', 'count'), CONNECTIONS_PERMITTED)
def test_handler_github_permission(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    user: str,
    allowed: tuple[str, ...],
    count: int
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = allowed), update_user = 'UXXX1')

    with respx.mock(assert_all_called = False) as router:

        router.post(threadvault.github.oauth.CODE_URL).respond(200, json = {'error': 'device_flow_disabled', 'error_description': 'xxx'})

        assert press(application, user, threadvault.slack.view.CONNECTION_ACTION).status == 200

    assert len(calls(workspace, 'views.open')) == count

def test_handler_notice_owner(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(owner_id = 'UXXX3'), update_user = 'UXXX1')
    manager.save(TOKENS_SAVED)

    assert press(application, 'UXXX3', threadvault.slack.view.DISCONNECTION_ACTION).status == 200
    assert [arguments['channel'] for arguments in calls(workspace, 'chat.postMessage')] == ['UXXX1', 'UXXX2', 'UXXX3']

def test_handler_notice_failure(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    slack: slack_sdk.web.WebClient,
    manager: threadvault.github.token.TokenManager
) -> None:

    channels = []

    def post(
        *,
        channel: str,
        **_: object
    ) -> None:

        if channel == 'UXXX1': raise slack_sdk.errors.SlackApiError('xxx', {'ok': False, 'error': 'channel_not_found'})

        channels.append(channel)

    monkeypatch.setattr(slack, 'chat_postMessage', post)
    manager.save(TOKENS_SAVED)

    assert press(application, 'UXXX1', threadvault.slack.view.DISCONNECTION_ACTION).status == 200
    assert channels == ['UXXX2']

def test_handler_destination_offer(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx1'), update_user = 'UXXX1')
    manager.save(TOKENS_SAVED)
    options = json.loads(suggest(application, 'UXXX1', '').body)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations/1/repositories').respond(200, json = REPOSITORIES_RESPONDED)

        assert press(application, 'UXXX1', threadvault.slack.view.DESTINATION_ACTION).status == 200

    assert options == {'options': []}
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.offer(current = 'xxx/xxx1', language = 'ja')}]
    assert json.loads(suggest(application, 'UXXX1', 'XXX2').body) == {'options': threadvault.slack.view.suggest(['xxx/xxx2'])}

def test_handler_destination_choice(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').respond(200, json = {'full_name': 'xxx/xxx', 'private': True})
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)
        response = submit(application, 'UXXX1', chosen('xxx/xxx'))

    assert json.loads(response.body) == {'response_action': 'update', 'view': threadvault.slack.view.settle(repository = 'xxx/xxx', outcome = 'check', language = 'ja')}
    assert threadvault.customisation.SettingsIO(database).load('TXXX').repository_name == 'xxx/xxx'
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.settle(repository = 'xxx/xxx', outcome = 'success', language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx', running = False, role = 'owner', slug = 'xxx', language = 'ja')}]
    assert calls(workspace, 'chat.postMessage') == [{'channel': admin, 'text': threadvault.localisation.translate('notice.destination', 'ja', user = 'UXXX1', repository = 'xxx/xxx')} for admin in ('UXXX1', 'UXXX2')]

def test_handler_destination_concurrency(
    application: slack_bolt.App,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    def answer(
        _: httpx.Request
    ) -> httpx.Response:

        threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = ('UXXX2',)), update_user = 'UXXX1')

        return httpx.Response(200, json = {'full_name': 'xxx/xxx', 'private': True})

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').mock(side_effect = answer)
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert submit(application, 'UXXX1', chosen('xxx/xxx')).status == 200

    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings(repository_name = 'xxx/xxx', admins_allowed = ('UXXX2',))

@pytest.mark.parametrize(('repository', 'response', 'outcome', 'message'), DESTINATIONS_REFUSED)
def test_handler_destination_refusal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager,
    repository: str,
    response: httpx.Response,
    outcome: threadvault.slack.view.DestinationOutcome,
    message: str
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock(assert_all_called = False) as router:

        router.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').mock(return_value = response)

        assert submit(application, 'UXXX1', chosen(repository)).status == 200

    assert threadvault.customisation.SettingsIO(database).load('TXXX').repository_name is None
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.settle(repository = repository, outcome = outcome, language = 'ja', message = message)}]
    assert calls(workspace, 'chat.postMessage') == []

def test_handler_creation_offer(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = {'total_count': 2, 'installations': [{'id': 1, 'account': {'login': 'XXX2'}}, {'id': 2, 'account': {'login': 'xxx1'}}]})

        assert press(application, 'UXXX1', threadvault.slack.view.CREATION_ACTION).status == 200

    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.propose(accounts = None, language = 'ja')}]
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.propose(accounts = ['xxx1', 'XXX2'], language = 'ja')}]

def test_handler_creation_unavailability(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(500, text = 'xxx')

        assert press(application, 'UXXX1', threadvault.slack.view.CREATION_ACTION).status == 200

    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.establish(repository = '', outcome = 'failure', language = 'ja', message = 'GitHub answered 500 to GET /user/installations?per_page=100: xxx')}]

def test_handler_creation_success(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
        route = respx.post(f'{threadvault.github.rest.API_URL}/user/repos').respond(201, json = {'full_name': 'xxx/xxx1', 'private': True})
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)
        response = submit(application, 'UXXX1', named('xxx', 'xxx1'))

    assert json.loads(response.body) == {'response_action': 'update', 'view': threadvault.slack.view.establish(repository = 'xxx/xxx1', outcome = 'check', language = 'ja')}
    assert json.loads(route.calls.last.request.content) == {'name': 'xxx1', 'private': True, 'auto_init': True}
    assert threadvault.customisation.SettingsIO(database).load('TXXX').repository_name == 'xxx/xxx1'
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.establish(repository = 'xxx/xxx1', outcome = 'success', language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx1', running = False, role = 'owner', slug = 'xxx', language = 'ja')}]
    assert calls(workspace, 'chat.postMessage') == [{'channel': admin, 'text': threadvault.localisation.translate('notice.creation', 'ja', user = 'UXXX1', repository = 'xxx/xxx1')} for admin in ('UXXX1', 'UXXX2')]

def test_handler_creation_concurrency(
    application: slack_bolt.App,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    def answer(
        _: httpx.Request
    ) -> httpx.Response:

        threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = ('UXXX2',)), update_user = 'UXXX1')

        return httpx.Response(201, json = {'full_name': 'xxx/xxx', 'private': True})

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
        respx.post(f'{threadvault.github.rest.API_URL}/user/repos').mock(side_effect = answer)
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert submit(application, 'UXXX1', named('xxx', 'xxx')).status == 200

    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings(repository_name = 'xxx/xxx', admins_allowed = ('UXXX2',))

@pytest.mark.parametrize(('name', 'response', 'message'), CREATIONS_FAILED)
def test_handler_creation_failure(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager,
    name: str,
    response: httpx.Response,
    message: str
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock(assert_all_called = False) as router:

        router.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
        router.post(f'{threadvault.github.rest.API_URL}/user/repos').mock(return_value = response)

        assert submit(application, 'UXXX1', named('xxx', name)).status == 200

    assert threadvault.customisation.SettingsIO(database).load('TXXX').repository_name is None
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.establish(repository = f'xxx/{name}', outcome = 'failure', language = 'ja', message = message)}]
    assert calls(workspace, 'chat.postMessage') == []

def test_handler_backup_start(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    runs = []

    def publish(
        _: slack_sdk.web.WebClient,
        settings: threadvault.customisation.Settings,
        *,
        directory: pathlib.Path,
        full_name: str,
        token: collections.abc.Callable[[], str],
        days: int,
        limit: int | None,
        now: datetime.datetime
    ) -> list[threadvault.backup.runner.Result]:

        runs.append((settings.repository_name, full_name, directory.parts[-3:], token(), days, limit, now.tzinfo))

        return []

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)
    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx'), update_user = 'UXXX1')
    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert press(application, 'UXXX1', threadvault.slack.view.BACKUP_ACTION).status == 200

    assert runs == [('xxx/xxx', 'xxx/xxx', ('vaults', 'xxx', 'xxx'), 'ghu_xxx', 30, None, datetime.UTC)]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx', running = running, role = 'owner', slug = 'xxx', language = 'ja')} for running in (True, False)]

@pytest.mark.parametrize('error', ERRORS_BACKUP)
def test_handler_backup_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    error: Exception
) -> None:

    monkeypatch.setattr(threadvault.backup.runner, 'publish', unittest.mock.Mock(side_effect = error))
    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx'), update_user = 'UXXX1')

    assert press(application, 'UXXX1', threadvault.slack.view.BACKUP_ACTION).status == 200
    assert 'Backup failed: xxx' in caplog.text
    assert [arguments['view'] for arguments in calls(workspace, 'views.publish')] == [threadvault.slack.view.home(github = 'disconnected', destination = 'xxx/xxx', running = running, role = 'owner', slug = 'xxx', language = 'ja') for running in (True, False)]

def test_handler_backup_absence(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    publish = unittest.mock.Mock(return_value = [])

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)

    assert press(application, 'UXXX1', threadvault.slack.view.BACKUP_ACTION).status == 200
    assert not publish.called
    assert [arguments['view'] for arguments in calls(workspace, 'views.publish')] == [threadvault.slack.view.home(github = 'disconnected', destination = None, running = running, role = 'owner', slug = 'xxx', language = 'ja') for running in (True, False)]

def test_handler_backup_exclusivity(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database
) -> None:

    def busy(
        _: threadvault.worker.Worker
    ) -> bool:

        return True

    def start(
        *_: object
    ) -> bool:

        return False

    publish = unittest.mock.Mock(return_value = [])

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)
    monkeypatch.setattr(threadvault.worker.Worker, 'busy', busy)
    monkeypatch.setattr(threadvault.worker.Worker, 'start', start)
    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx'), update_user = 'UXXX1')

    assert press(application, 'UXXX1', threadvault.slack.view.BACKUP_ACTION).status == 200
    assert not publish.called
    assert [arguments['view'] for arguments in calls(workspace, 'views.publish')] == [threadvault.slack.view.home(github = 'disconnected', destination = 'xxx/xxx', running = True, role = 'owner', slug = 'xxx', language = 'ja')]

def test_handler_permission_grant(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database
) -> None:

    assert press(application, 'UXXX1', threadvault.slack.view.PERMISSIONS_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.permit(admins = ['UXXX2'], allowed = (), language = 'ja')}]

    review = submit(application, 'UXXX1', checked(['UXXX2']))
    confirmation = threadvault.slack.view.review(granted = ['UXXX2'], revoked = [], language = 'ja')

    assert json.loads(review.body) == {'response_action': 'push', 'view': confirmation}
    assert json.loads(submit(application, 'UXXX1', confirmation).body) == {'response_action': 'clear'}
    assert threadvault.customisation.SettingsIO(database).load('TXXX').admins_allowed == ('UXXX2',)
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX1', 'UXXX2']
    assert calls(workspace, 'chat.postMessage') == [{'channel': 'UXXX2', 'text': threadvault.localisation.translate('notice.grant', 'ja', owner = 'UXXX1', product = threadvault.product.NAME)}, {'channel': 'UXXX1', 'text': threadvault.localisation.translate('notice.grant.done', 'ja', user = 'UXXX2', product = threadvault.product.NAME)}]

def test_handler_permission_revocation(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = ('UXXX2',)), update_user = 'UXXX1')

    review = submit(application, 'UXXX1', checked([]))
    confirmation = threadvault.slack.view.review(granted = [], revoked = ['UXXX2'], language = 'ja')

    assert json.loads(review.body) == {'response_action': 'push', 'view': confirmation}
    assert json.loads(submit(application, 'UXXX1', confirmation).body) == {'response_action': 'clear'}
    assert threadvault.customisation.SettingsIO(database).load('TXXX').admins_allowed == ()
    assert calls(workspace, 'chat.postMessage') == [{'channel': 'UXXX2', 'text': threadvault.localisation.translate('notice.revocation', 'ja', owner = 'UXXX1', product = threadvault.product.NAME)}, {'channel': 'UXXX1', 'text': threadvault.localisation.translate('notice.revocation.done', 'ja', user = 'UXXX2', product = threadvault.product.NAME)}]

def test_handler_permission_unchanged(
    application: slack_bolt.App,
    database: threadvault.storage.Database
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = ('UXXX2', 'UXXX9')), update_user = 'UXXX1')

    review = submit(application, 'UXXX1', checked(['UXXX2']))

    assert json.loads(review.body) == {'response_action': 'errors', 'errors': {f'{threadvault.slack.view.ADMINS_INPUT}0': threadvault.localisation.translate('permissions.unchanged', 'ja')}}

def test_handler_permission_owner(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = ('UXXX2',)), update_user = 'UXXX1')

    assert press(application, 'UXXX2', threadvault.slack.view.PERMISSIONS_ACTION).status == 200
    assert submit(application, 'UXXX2', threadvault.slack.view.review(granted = [], revoked = ['UXXX2'], language = 'ja')).status == 200
    assert calls(workspace, 'views.open') == []
    assert threadvault.customisation.SettingsIO(database).load('TXXX').admins_allowed == ('UXXX2',)

def test_handler_permission_successor(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(owner_id = 'UXXX2', admins_allowed = ('UXXX1',)), update_user = 'UXXX1')

    assert press(application, 'UXXX2', threadvault.slack.view.PERMISSIONS_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.permit(admins = ['UXXX1'], allowed = ('UXXX1',), language = 'ja')}]
    assert json.loads(submit(application, 'UXXX2', checked([])).body) == {'response_action': 'push', 'view': threadvault.slack.view.review(granted = [], revoked = ['UXXX1'], language = 'ja')}

@pytest.mark.parametrize(('allowed', 'expected'), TRANSFERS_ALLOWED)
def test_handler_transfer_completion(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    allowed: tuple[str, ...],
    expected: tuple[str, ...]
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = allowed), update_user = 'UXXX1')

    assert press(application, 'UXXX1', threadvault.slack.view.TRANSFER_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.cede(language = 'ja')}]

    nomination = submit(application, 'UXXX1', selected('UXXX2'))
    confirmation = threadvault.slack.view.nominate(successor = 'UXXX2', language = 'ja')

    assert json.loads(nomination.body) == {'response_action': 'push', 'view': confirmation}
    assert json.loads(submit(application, 'UXXX1', confirmation).body) == {'response_action': 'clear'}
    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings(owner_id = 'UXXX2', admins_allowed = expected)
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, role = 'operator', slug = 'xxx', language = 'ja')}, {'user_id': 'UXXX2', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, role = 'owner', slug = 'xxx', language = 'ja')}]
    assert calls(workspace, 'chat.postMessage') == [{'channel': 'UXXX2', 'text': threadvault.localisation.translate('notice.ownership', 'ja', owner = 'UXXX1', product = threadvault.product.NAME)}, {'channel': 'UXXX1', 'text': threadvault.localisation.translate('notice.ownership.done', 'ja', user = 'UXXX2', product = threadvault.product.NAME)}]

@pytest.mark.parametrize('successor', SUCCESSORS_INVALID)
def test_handler_transfer_refusal(
    application: slack_bolt.App,
    successor: str
) -> None:

    nomination = submit(application, 'UXXX1', selected(successor))

    assert json.loads(nomination.body) == {'response_action': 'errors', 'errors': {threadvault.slack.view.SUCCESSOR_INPUT: threadvault.localisation.translate('transfer.invalid', 'ja')}}

def test_handler_transfer_owner(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(admins_allowed = ('UXXX2',)), update_user = 'UXXX1')

    assert press(application, 'UXXX2', threadvault.slack.view.TRANSFER_ACTION).status == 200
    assert submit(application, 'UXXX2', selected('UXXX2')).body == ''
    assert submit(application, 'UXXX2', threadvault.slack.view.nominate(successor = 'UXXX2', language = 'ja')).status == 200
    assert calls(workspace, 'views.open') == []
    assert threadvault.customisation.SettingsIO(database).load('TXXX').owner_id is None

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
