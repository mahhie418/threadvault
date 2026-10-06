import typing

import pytest

import threadvault.github.oauth
import threadvault.slack.permission
import threadvault.slack.view

CODE = threadvault.github.oauth.Code(device_code = 'xxx', user_code = 'XXXX-XXXX', verification_uri = 'https://github.com/login/device', interval = 5)

STATES_HOME = [
    ({'connected': True, 'destination': 'xxx/xxx', 'role': 'owner', 'language': 'ja'}, ['*GitHub*\n連携済み', '*保存先*\n<https://github.com/xxx/xxx|xxx/xxx>']),
    ({'connected': True, 'destination': 'xxx/xxx', 'role': 'member', 'language': 'en'}, ['*GitHub*\nConnected']),
    ({'connected': False, 'destination': None, 'role': 'admin', 'language': 'en'}, ['*GitHub*\nNot connected', '*Destination*\nNot chosen'])
]

ROLES_MESSAGE = [
    ('owner', ['You are the owner.']),
    ('admin', ['You are an admin.']),
    ('member', [])
]

VIEWERS_MESSAGE = [
    ({'connected': True, 'role': 'owner'}, []),
    ({'connected': False, 'role': 'owner'}, [threadvault.slack.view.CONNECTION_ACTION]),
    ({'connected': False, 'role': 'admin'}, [threadvault.slack.view.CONNECTION_ACTION]),
    ({'connected': False, 'role': 'member'}, [])
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

    view = threadvault.slack.view.home(**state)

    assert view['type'] == 'home'
    assert [field['text'] for block in view['blocks'] if 'fields' in block for field in block['fields']] == texts

@pytest.mark.parametrize(('role', 'texts'), ROLES_MESSAGE)
def test_view_home_role(
    role: threadvault.slack.permission.Role,
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(connected = False, destination = None, role = role, language = 'en')

    assert [element['text'] for block in view['blocks'] if block['type'] == 'context' for element in block['elements']] == texts

@pytest.mark.parametrize(('state', 'actions'), VIEWERS_MESSAGE)
def test_view_home_connection(
    state: dict[str, typing.Any],
    actions: list[str]
) -> None:

    view = threadvault.slack.view.home(**state, destination = None, language = 'en')

    assert [element['action_id'] for block in view['blocks'] if block['type'] == 'actions' for element in block['elements']] == actions

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
