import json
import typing

import pytest

import threadvault.github.oauth
import threadvault.slack.permission
import threadvault.slack.view

CODE = threadvault.github.oauth.Code(device_code = 'xxx', user_code = 'XXXX-XXXX', verification_uri = 'https://github.com/login/device', interval = 5)

STATES_HOME = [
    ({'github': 'connected', 'destination': 'xxx/xxx', 'role': 'owner', 'language': 'ja'}, ['*GitHub*\n連携済み', '*保存先*\n<https://github.com/xxx/xxx|xxx/xxx>']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'role': 'member', 'language': 'en'}, ['*GitHub*\nConnected']),
    ({'github': 'disconnected', 'destination': None, 'role': 'admin', 'language': 'en'}, ['*GitHub*\nNot connected', '*Destination*\nNot chosen']),
    ({'github': 'uninstalled', 'destination': None, 'role': 'admin', 'language': 'en'}, ['*GitHub*\nConnected', '*Destination*\nNot chosen'])
]

ROLES_MESSAGE = [
    ('owner', ['You are the owner.']),
    ('operator', ['You are an admin with permission to operate the app.']),
    ('admin', ['You are an admin without permission to operate the app.']),
    ('member', [])
]

VIEWERS_MESSAGE = [
    ({'github': 'connected', 'role': 'owner'}, [(threadvault.slack.view.DISCONNECTION_ACTION, True), (threadvault.slack.view.PERMISSIONS_ACTION, False), (threadvault.slack.view.TRANSFER_ACTION, False)]),
    ({'github': 'connected', 'role': 'operator'}, [(threadvault.slack.view.DISCONNECTION_ACTION, True)]),
    ({'github': 'connected', 'role': 'admin'}, []),
    ({'github': 'disconnected', 'role': 'owner'}, [(threadvault.slack.view.CONNECTION_ACTION, False), (threadvault.slack.view.PERMISSIONS_ACTION, False), (threadvault.slack.view.TRANSFER_ACTION, False)]),
    ({'github': 'disconnected', 'role': 'operator'}, [(threadvault.slack.view.CONNECTION_ACTION, False)]),
    ({'github': 'disconnected', 'role': 'member'}, []),
    ({'github': 'uninstalled', 'role': 'operator'}, [(threadvault.slack.view.DISCONNECTION_ACTION, True)])
]

VIEWERS_INSTALLATION = [
    ({'github': 'connected', 'role': 'owner'}, []),
    ({'github': 'disconnected', 'role': 'owner'}, []),
    ({'github': 'uninstalled', 'role': 'owner'}, ['*GitHub App*\nNot installed yet. <https://github.com/apps/xxx1/installations/new|Install it> on the account or organisation that will hold the vault.']),
    ({'github': 'uninstalled', 'role': 'operator'}, ['*GitHub App*\nNot installed yet. <https://github.com/apps/xxx1/installations/new|Install it> on the account or organisation that will hold the vault.']),
    ({'github': 'uninstalled', 'role': 'admin'}, []),
    ({'github': 'uninstalled', 'role': 'member'}, [])
]

ADMINS_ALLOWED = [
    (['UXXX1', 'UXXX2'], ('UXXX2',), [['UXXX1', 'UXXX2']], [['UXXX2']]),
    ([f'UXXX{index}' for index in range(12)], ('UXXX0', 'UXXX11'), [[f'UXXX{index}' for index in range(10)], ['UXXX10', 'UXXX11']], [['UXXX0'], ['UXXX11']]),
    (['UXXX1'], (), [['UXXX1']], [[]])
]

CONNECTIONS_MESSAGE = [
    (None, 'Requesting a code from GitHub…'),
    (CODE, 'Open https://github.com/login/device and enter this code:\n*XXXX-XXXX*\nThis window shows the result once you have finished on GitHub.')
]

ERRORS_MESSAGE = [
    (None, 'GitHub is connected.'),
    (threadvault.github.oauth.OAuthError('access_denied', 'xxx'), 'The request was declined on GitHub.'),
    (threadvault.github.oauth.OAuthError('expired_token', 'xxx'), 'The code has expired. Close this window and try again.'),
    (threadvault.github.oauth.OAuthError('connection', 'xxx'), 'GitHub could not be connected: xxx')
]

@pytest.mark.parametrize(('state', 'texts'), STATES_HOME)
def test_view_home_status(
    state: dict[str, typing.Any],
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(**state, slug = 'xxx')

    assert view['type'] == 'home'
    assert [field['text'] for block in view['blocks'] if 'fields' in block for field in block['fields']] == texts

@pytest.mark.parametrize(('role', 'texts'), ROLES_MESSAGE)
def test_view_home_role(
    role: threadvault.slack.permission.Role,
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(github = 'disconnected', destination = None, role = role, slug = 'xxx', language = 'en')

    assert [element['text'] for block in view['blocks'] if block['type'] == 'context' for element in block['elements']] == texts

@pytest.mark.parametrize(('state', 'buttons'), VIEWERS_MESSAGE)
def test_view_home_connection(
    state: dict[str, typing.Any],
    buttons: list[tuple[str, bool]]
) -> None:

    view = threadvault.slack.view.home(**state, destination = None, slug = 'xxx', language = 'en')

    assert [(element['action_id'], 'confirm' in element) for block in view['blocks'] if block['type'] == 'actions' for element in block['elements']] == buttons

@pytest.mark.parametrize(('state', 'texts'), VIEWERS_INSTALLATION)
def test_view_home_installation(
    state: dict[str, typing.Any],
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(**state, destination = None, slug = 'xxx1', language = 'en')

    assert [block['text']['text'] for block in view['blocks'] if 'text' in block] == texts

@pytest.mark.parametrize(('code', 'text'), CONNECTIONS_MESSAGE)
def test_view_connection_establishment(
    code: threadvault.github.oauth.Code | None,
    text: str
) -> None:

    view = threadvault.slack.view.connect(code = code, language = 'en')

    assert view['type'] == 'modal'
    assert [block['text']['text'] for block in view['blocks']] == [text]

@pytest.mark.parametrize(('error', 'text'), ERRORS_MESSAGE)
def test_view_connection_response(
    error: threadvault.github.oauth.OAuthError | None,
    text: str
) -> None:

    view = threadvault.slack.view.respond(error = error, language = 'en')

    assert view['type'] == 'modal'
    assert [block['text']['text'] for block in view['blocks']] == [text]

@pytest.mark.parametrize(('admins', 'allowed', 'groups', 'chosen'), ADMINS_ALLOWED)
def test_view_permission_choice(
    admins: list[str],
    allowed: tuple[str, ...],
    groups: list[list[str]],
    chosen: list[list[str]]
) -> None:

    view = threadvault.slack.view.permit(admins = admins, allowed = allowed, language = 'en')
    inputs = [block for block in view['blocks'] if block['type'] == 'input']

    assert view['callback_id'] == threadvault.slack.view.PERMISSIONS_CALLBACK
    assert [block['block_id'] for block in inputs] == [f'{threadvault.slack.view.ADMINS_INPUT}{index}' for index in range(len(groups))]
    assert [[option['value'] for option in block['element']['options']] for block in inputs] == groups
    assert [[option['value'] for option in block['element']['initial_options']] if 'initial_options' in block['element'] else [] for block in inputs] == chosen

def test_view_permission_confirmation() -> None:

    view = threadvault.slack.view.review(granted = ['UXXX1'], revoked = ['UXXX2'], language = 'en')

    assert view['callback_id'] == threadvault.slack.view.PERMISSIONS_CONFIRMATION
    assert json.loads(view['private_metadata']) == {'granted': ['UXXX1'], 'revoked': ['UXXX2']}
    assert [block['text']['text'] for block in view['blocks']] == ['Apply these changes?\n• Allow <@UXXX1> to operate the app\n• Withdraw the permission of <@UXXX2>']

def test_view_permission_absence() -> None:

    view = threadvault.slack.view.permit(admins = [], allowed = (), language = 'en')

    assert 'submit' not in view
    assert [block['text']['text'] for block in view['blocks']] == ['There are no admins other than you. Add their Slack user IDs to THREADVAULT_ADMIN_IDS first.']

def test_view_transfer_choice() -> None:

    view = threadvault.slack.view.cede(language = 'en')

    assert view['callback_id'] == threadvault.slack.view.TRANSFER_CALLBACK
    assert [block['text']['text'] for block in view['blocks'] if block['type'] == 'section'] == ['Choose the admin who becomes the owner. You stay an admin with permission to operate the app.']
    assert [(block['block_id'], block['element']) for block in view['blocks'] if block['type'] == 'input'] == [(threadvault.slack.view.SUCCESSOR_INPUT, {'type': 'users_select', 'action_id': threadvault.slack.view.SUCCESSOR_INPUT})]

def test_view_transfer_confirmation() -> None:

    view = threadvault.slack.view.nominate(successor = 'UXXX2', language = 'en')

    assert (view['callback_id'], view['private_metadata'], view['close']['text']) == (threadvault.slack.view.TRANSFER_CONFIRMATION, 'UXXX2', 'Back')
    assert [block['text']['text'] for block in view['blocks']] == ['Transfer the ownership to <@UXXX2>? You stay an admin with permission to operate the app.']
