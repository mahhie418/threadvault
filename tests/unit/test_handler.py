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
import threadvault.journal
import threadvault.localisation
import threadvault.product
import threadvault.schedule
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

ACTIONS_STARTED = [
    (threadvault.slack.view.BACKUP_ACTION, 30),
    (threadvault.slack.view.RESYNCHRONISATION_ACTION, None)
]

ACTIONS_REFUSED = [
    threadvault.slack.view.BACKUP_ACTION,
    threadvault.slack.view.RESYNCHRONISATION_ACTION
]

ERRORS_BACKUP = [
    threadvault.backup.runner.VaultError('xxx'),
    threadvault.backup.runner.LockError('xxx')
]

TIME_CHECKED = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)
SETTINGS_SCHEDULED = threadvault.customisation.Settings(repository_name = 'xxx/xxx', schedule_time = '12:00', workspace_timezone = 'Asia/Tokyo')

SETTINGS_IDLE = [
    threadvault.customisation.Settings(),
    threadvault.customisation.Settings(repository_name = 'xxx/xxx', schedule_enabled = False)
]

TIMES_PLANNED = [
    (datetime.datetime(2026, 10, 10, 15, 0, tzinfo = datetime.UTC), 0, datetime.datetime(2026, 10, 10, 15, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC), 1, datetime.datetime(2026, 10, 10, 3, 0, tzinfo = datetime.UTC)),
    (datetime.datetime(2026, 10, 8, 15, 0, tzinfo = datetime.UTC), 1, datetime.datetime(2026, 10, 10, 3, 0, tzinfo = datetime.UTC))
]

TIMEZONES_OFFERED = [
    ('UTC', 'Asia/Tokyo', 'Asia/Tokyo'),
    ('Europe/London', 'Asia/Tokyo', 'Europe/London'),
    ('UTC', None, 'UTC')
]

SETTINGS_CHANGED = [
    threadvault.customisation.Settings(repository_name = 'xxx/xxx', schedule_time = '12:00', workspace_timezone = 'Asia/Tokyo'),
    threadvault.customisation.Settings(repository_name = 'xxx/xxx', schedule_enabled = False)
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
    registration: tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]
) -> slack_bolt.App:

    return registration[0]

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

@pytest.fixture
def registration(
    monkeypatch: pytest.MonkeyPatch,
    slack: slack_sdk.web.WebClient,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]:

    def detach(
        function: collections.abc.Callable[[], None]
    ) -> None:

        function()

    application = slack_bolt.App(client = slack, process_before_response = True)
    monkeypatch.setattr(threadvault.slack.handler, 'detach', detach)

    return application, threadvault.slack.handler.register(application, threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX2', 'GITHUB_APP_CLIENT_ID': 'xxx', 'GITHUB_APP_SLUG': 'xxx', 'THREADVAULT_LANGUAGE_DISPLAY': 'ja'}), database, manager)

@pytest.fixture
def schedule(
    registration: tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]
) -> collections.abc.Callable[[str, datetime.datetime], None]:

    return registration[1]

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
    action: str,
    value: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'block_suggestion', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'action_id': action, 'block_id': action, 'value': value}, mode = 'socket_mode'))

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

def configured(
    settings: threadvault.customisation.Settings
) -> dict[str, typing.Any]:

    return {'callback_id': threadvault.slack.view.SETTINGS_CALLBACK, 'state': {'values': {threadvault.slack.view.SCHEDULE_INPUT: {threadvault.slack.view.SCHEDULE_INPUT: {'type': 'checkboxes', 'selected_options': [{'value': 'enabled'}] if settings.schedule_enabled else []}}, threadvault.slack.view.TIME_INPUT: {threadvault.slack.view.TIME_INPUT: {'type': 'timepicker', 'selected_time': settings.schedule_time}}, threadvault.slack.view.TIMEZONE_ACTION: {threadvault.slack.view.TIMEZONE_ACTION: {'type': 'external_select', 'selected_option': {'text': {'type': 'plain_text', 'text': settings.workspace_timezone}, 'value': settings.workspace_timezone}}}, threadvault.slack.view.MODE_INPUT: {threadvault.slack.view.MODE_INPUT: {'type': 'radio_buttons', 'selected_option': {'value': settings.channel_mode}}}, threadvault.slack.view.CHANNELS_INPUT: {threadvault.slack.view.CHANNELS_INPUT: {'type': 'multi_conversations_select', 'selected_conversations': list(settings.channels_selected)}}, threadvault.slack.view.ATTACHMENTS_INPUT: {threadvault.slack.view.ATTACHMENTS_INPUT: {'type': 'checkboxes', 'selected_options': [{'value': 'enabled'}] if settings.attachments_enabled else []}}, threadvault.slack.view.SIZE_INPUT: {threadvault.slack.view.SIZE_INPUT: {'type': 'number_input', 'value': str(settings.attachment_size_maximum)}}, threadvault.slack.view.LANGUAGE_INPUT: {threadvault.slack.view.LANGUAGE_INPUT: {'type': 'radio_buttons', 'selected_option': {'value': settings.markdown_language}}}}}}

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
    threadvault.schedule.ScheduleIO(database).save('TXXX', TIME_CHECKED)
    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert home(application, user, 'home').status == 200

    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx', running = False, last = None, planned = TIME_CHECKED, role = role, slug = 'xxx', language = 'ja')}]

def test_handler_home_locale(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['locale'] = 'en-GB'

    assert home(application, 'UXXX1', 'home').status == 200
    assert calls(workspace, 'users.info') == [{'user': 'UXXX1', 'include_locale': True}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'en')}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}] * count

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
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}]
    assert calls(workspace, 'chat.postMessage') == [{'channel': 'UXXX1', 'text': threadvault.localisation.translate('notice.connection', 'ja', user = 'UXXX1')}, {'channel': 'UXXX2', 'text': threadvault.localisation.translate('notice.connection', 'en', user = 'UXXX1')}]

def test_handler_github_disconnection(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    assert press(application, 'UXXX1', threadvault.slack.view.DISCONNECTION_ACTION).status == 200
    assert not manager.connected()
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}]
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

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = github, destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}]

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

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'expired', destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}]

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
    options = json.loads(suggest(application, 'UXXX1', threadvault.slack.view.REPOSITORY_ACTION, '').body)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)
        respx.get(f'{threadvault.github.rest.API_URL}/user/installations/1/repositories').respond(200, json = REPOSITORIES_RESPONDED)

        assert press(application, 'UXXX1', threadvault.slack.view.DESTINATION_ACTION).status == 200

    assert options == {'options': []}
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.offer(current = 'xxx/xxx1', language = 'ja')}]
    assert json.loads(suggest(application, 'UXXX1', threadvault.slack.view.REPOSITORY_ACTION, 'XXX2').body) == {'options': threadvault.slack.view.suggest(['xxx/xxx2'])}

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

    planned = threadvault.schedule.ScheduleIO(database).load('TXXX')

    assert json.loads(response.body) == {'response_action': 'update', 'view': threadvault.slack.view.settle(repository = 'xxx/xxx', outcome = 'check', language = 'ja')}
    assert threadvault.customisation.SettingsIO(database).load('TXXX').repository_name == 'xxx/xxx'
    assert planned is not None
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.settle(repository = 'xxx/xxx', outcome = 'success', language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx', running = False, last = None, planned = planned, role = 'owner', slug = 'xxx', language = 'ja')}]
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

    planned = threadvault.schedule.ScheduleIO(database).load('TXXX')

    assert json.loads(response.body) == {'response_action': 'update', 'view': threadvault.slack.view.establish(repository = 'xxx/xxx1', outcome = 'check', language = 'ja')}
    assert json.loads(route.calls.last.request.content) == {'name': 'xxx1', 'private': True, 'auto_init': True}
    assert threadvault.customisation.SettingsIO(database).load('TXXX').repository_name == 'xxx/xxx1'
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': threadvault.slack.view.establish(repository = 'xxx/xxx1', outcome = 'success', language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx1', running = False, last = None, planned = planned, role = 'owner', slug = 'xxx', language = 'ja')}]
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

@pytest.mark.parametrize(('action', 'days'), ACTIONS_STARTED)
def test_handler_backup_start(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager,
    action: str,
    days: int | None
) -> None:

    runs = []

    def publish(
        _: slack_sdk.web.WebClient,
        settings: threadvault.customisation.Settings,
        *,
        directory: pathlib.Path,
        full_name: str,
        token: collections.abc.Callable[[], str],
        days: int | None,
        limit: int | None,
        now: datetime.datetime
    ) -> tuple[list[threadvault.backup.runner.Result], str]:

        runs.append((settings.repository_name, full_name, directory.parts[-3:], token(), days, limit, now.tzinfo))

        return [], 'xxx'

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)
    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx'), update_user = 'UXXX1')
    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = INSTALLATIONS_RESPONDED)

        assert press(application, 'UXXX1', action).status == 200

    last = threadvault.journal.RunIO(database).load('TXXX')
    planned = threadvault.schedule.ScheduleIO(database).load('TXXX')

    assert runs == [('xxx/xxx', 'xxx/xxx', ('vaults', 'xxx', 'xxx'), 'ghu_xxx', days, None, datetime.UTC)]
    assert last == threadvault.journal.Run(completion = unittest.mock.ANY, repository = 'xxx/xxx', commit = 'xxx', reason = None)
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'connected', destination = 'xxx/xxx', running = running, last = run, planned = planned, role = 'owner', slug = 'xxx', language = 'ja')} for running, run in ((True, None), (False, last))]
    assert calls(workspace, 'chat.postMessage') == []

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

    last = threadvault.journal.RunIO(database).load('TXXX')
    planned = threadvault.schedule.ScheduleIO(database).load('TXXX')

    assert 'Backup failed: xxx' in caplog.text
    assert last == threadvault.journal.Run(completion = unittest.mock.ANY, repository = 'xxx/xxx', commit = None, reason = 'xxx')
    assert [arguments['view'] for arguments in calls(workspace, 'views.publish')] == [threadvault.slack.view.home(github = 'disconnected', destination = 'xxx/xxx', running = running, last = run, planned = planned, role = 'owner', slug = 'xxx', language = 'ja') for running, run in ((True, None), (False, last))]
    assert calls(workspace, 'chat.postMessage') == [{'channel': admin, 'text': threadvault.localisation.translate('notice.failure', 'ja', message = 'xxx')} for admin in ('UXXX1', 'UXXX2')]

def test_handler_backup_absence(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    publish = unittest.mock.Mock(return_value = [])

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)

    assert press(application, 'UXXX1', threadvault.slack.view.BACKUP_ACTION).status == 200
    assert not publish.called
    assert [arguments['view'] for arguments in calls(workspace, 'views.publish')] == [threadvault.slack.view.home(github = 'disconnected', destination = None, running = running, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja') for running in (True, False)]

@pytest.mark.parametrize('action', ACTIONS_REFUSED)
def test_handler_backup_exclusivity(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    action: str
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

    assert press(application, 'UXXX1', action).status == 200

    planned = threadvault.schedule.ScheduleIO(database).load('TXXX')

    assert not publish.called
    assert [arguments['view'] for arguments in calls(workspace, 'views.publish')] == [threadvault.slack.view.home(github = 'disconnected', destination = 'xxx/xxx', running = True, last = None, planned = planned, role = 'owner', slug = 'xxx', language = 'ja')]

def test_handler_schedule_plan(
    monkeypatch: pytest.MonkeyPatch,
    database: threadvault.storage.Database,
    schedule: collections.abc.Callable[[str, datetime.datetime], None]
) -> None:

    publish = unittest.mock.Mock(return_value = ([], 'xxx'))

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)
    threadvault.customisation.SettingsIO(database).save('TXXX', SETTINGS_SCHEDULED, update_user = 'UXXX1')

    schedule('TXXX', TIME_CHECKED)

    assert not publish.called
    assert threadvault.schedule.ScheduleIO(database).load('TXXX') == datetime.datetime(2026, 10, 10, 3, 0, tzinfo = datetime.UTC)

@pytest.mark.parametrize(('stored', 'count', 'planned'), TIMES_PLANNED)
def test_handler_schedule_timing(
    monkeypatch: pytest.MonkeyPatch,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager,
    schedule: collections.abc.Callable[[str, datetime.datetime], None],
    stored: datetime.datetime,
    count: int,
    planned: datetime.datetime
) -> None:

    runs = []

    def publish(
        _: slack_sdk.web.WebClient,
        settings: threadvault.customisation.Settings,
        *,
        directory: pathlib.Path,
        full_name: str,
        token: collections.abc.Callable[[], str],
        days: int | None,
        limit: int | None,
        now: datetime.datetime
    ) -> tuple[list[threadvault.backup.runner.Result], str]:

        runs.append((settings.repository_name, full_name, directory.parts[-3:], token(), days, limit, now.tzinfo))

        return [], 'xxx'

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)
    threadvault.customisation.SettingsIO(database).save('TXXX', SETTINGS_SCHEDULED, update_user = 'UXXX1')
    threadvault.schedule.ScheduleIO(database).save('TXXX', stored)
    manager.save(TOKENS_SAVED)

    schedule('TXXX', TIME_CHECKED)

    assert runs == [('xxx/xxx', 'xxx/xxx', ('vaults', 'xxx', 'xxx'), 'ghu_xxx', 30, None, datetime.UTC)] * count
    assert threadvault.schedule.ScheduleIO(database).load('TXXX') == planned
    assert calls(workspace, 'views.publish') == []

@pytest.mark.parametrize('settings', SETTINGS_IDLE)
def test_handler_schedule_idleness(
    monkeypatch: pytest.MonkeyPatch,
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    schedule: collections.abc.Callable[[str, datetime.datetime], None],
    settings: threadvault.customisation.Settings
) -> None:

    publish = unittest.mock.Mock(return_value = ([], 'xxx'))

    monkeypatch.setattr(threadvault.backup.runner, 'publish', publish)
    threadvault.customisation.SettingsIO(database).save('TXXX', settings, update_user = 'UXXX1')
    threadvault.schedule.ScheduleIO(database).save('TXXX', TIME_CHECKED)

    schedule('TXXX', TIME_CHECKED)

    assert home(application, 'UXXX1', 'home').status == 200
    assert not publish.called
    assert threadvault.schedule.ScheduleIO(database).load('TXXX') == TIME_CHECKED
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = settings.repository_name, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}]

def test_handler_schedule_exclusivity(
    monkeypatch: pytest.MonkeyPatch,
    database: threadvault.storage.Database,
    schedule: collections.abc.Callable[[str, datetime.datetime], None]
) -> None:

    def start(
        *_: object
    ) -> bool:

        return False

    monkeypatch.setattr(threadvault.worker.Worker, 'start', start)
    threadvault.customisation.SettingsIO(database).save('TXXX', SETTINGS_SCHEDULED, update_user = 'UXXX1')
    threadvault.schedule.ScheduleIO(database).save('TXXX', TIME_CHECKED)

    schedule('TXXX', TIME_CHECKED)

    assert threadvault.schedule.ScheduleIO(database).load('TXXX') == TIME_CHECKED

@pytest.mark.parametrize(('saved', 'own', 'shown'), TIMEZONES_OFFERED)
def test_handler_settings_offer(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    saved: str,
    own: str | None,
    shown: str
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['tz'] = own
    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(workspace_timezone = saved), update_user = 'UXXX1')

    assert press(application, 'UXXX1', threadvault.slack.view.SETTINGS_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': threadvault.slack.view.configure(workspace = threadvault.customisation.Settings(workspace_timezone = shown), language = 'ja')}]

def test_handler_settings_search(
    application: slack_bolt.App
) -> None:

    assert json.loads(suggest(application, 'UXXX1', threadvault.slack.view.TIMEZONE_ACTION, 'tokyo').body) == {'options': threadvault.slack.view.suggest(['Asia/Tokyo'])}

@pytest.mark.parametrize('settings', SETTINGS_CHANGED)
def test_handler_settings_change(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: threadvault.storage.Database,
    settings: threadvault.customisation.Settings
) -> None:

    threadvault.customisation.SettingsIO(database).save('TXXX', threadvault.customisation.Settings(repository_name = 'xxx/xxx'), update_user = 'UXXX1')
    threadvault.schedule.ScheduleIO(database).save('TXXX', TIME_CHECKED)

    planned = threadvault.schedule.follow(datetime.datetime.now(datetime.UTC), settings.schedule_time, settings.workspace_timezone)

    assert submit(application, 'UXXX1', configured(settings)).body == ''
    assert threadvault.customisation.SettingsIO(database).load('TXXX') == settings
    assert threadvault.schedule.ScheduleIO(database).load('TXXX') == planned
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX1']

def test_handler_settings_retention(
    application: slack_bolt.App,
    database: threadvault.storage.Database
) -> None:

    threadvault.schedule.ScheduleIO(database).save('TXXX', TIME_CHECKED)

    assert submit(application, 'UXXX1', configured(threadvault.customisation.Settings())).body == ''
    assert threadvault.schedule.ScheduleIO(database).load('TXXX') == TIME_CHECKED

def test_handler_settings_channel(
    application: slack_bolt.App,
    database: threadvault.storage.Database
) -> None:

    assert submit(application, 'UXXX1', configured(threadvault.customisation.Settings(channel_mode = 'selected', channels_selected = ('CXXX2', 'CXXX1')))).body == ''
    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings(channel_mode = 'selected', channels_selected = ('CXXX1', 'CXXX2'))

def test_handler_settings_attachment(
    application: slack_bolt.App,
    database: threadvault.storage.Database
) -> None:

    assert submit(application, 'UXXX1', configured(threadvault.customisation.Settings(attachments_enabled = False, attachment_size_maximum = 50))).body == ''
    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings(attachments_enabled = False, attachment_size_maximum = 50)

def test_handler_settings_language(
    application: slack_bolt.App,
    database: threadvault.storage.Database
) -> None:

    assert submit(application, 'UXXX1', configured(threadvault.customisation.Settings(markdown_language = 'ja'))).body == ''
    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings(markdown_language = 'ja')

def test_handler_settings_absence(
    application: slack_bolt.App,
    database: threadvault.storage.Database
) -> None:

    response = submit(application, 'UXXX1', configured(threadvault.customisation.Settings(channel_mode = 'selected')))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {threadvault.slack.view.CHANNELS_INPUT: threadvault.localisation.translate('settings.channels.missing', 'ja')}}
    assert threadvault.customisation.SettingsIO(database).load('TXXX') == threadvault.customisation.Settings()

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
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, last = None, planned = None, role = 'operator', slug = 'xxx', language = 'ja')}, {'user_id': 'UXXX2', 'view': threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, last = None, planned = None, role = 'owner', slug = 'xxx', language = 'ja')}]
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
