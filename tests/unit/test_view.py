import typing

import pytest

import threadvault.slack.permission
import threadvault.slack.view

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
