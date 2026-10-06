import typing

import pytest

import threadvault.slack.view

STATES_HOME = [
    ({'connected': True, 'destination': 'xxx/xxx', 'role': 'admin'}, ['*GitHub*\nConnected', '*Destination*\n<https://github.com/xxx/xxx|xxx/xxx>']),
    ({'connected': True, 'destination': 'xxx/xxx', 'role': 'member'}, ['*GitHub*\nConnected']),
    ({'connected': False, 'destination': None, 'role': 'admin'}, ['*GitHub*\nNot connected', '*Destination*\nNot chosen'])
]

@pytest.mark.parametrize(('state', 'texts'), STATES_HOME)
def test_view_home_status(
    state: dict[str, typing.Any],
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(**state)

    assert view['type'] == 'home'
    assert [field['text'] for block in view['blocks'] if 'fields' in block for field in block['fields']] == texts
