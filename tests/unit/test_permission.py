import typing

import pytest
import slack_bolt
import slack_sdk

import threadvault.configuration
import threadvault.slack.permission

USERS_CLASSIFIED = [('UXXX1', 'owner'), ('UXXX2', 'admin'), ('UXXX3', 'member')]

REQUESTS_PERMITTED = [
    ({'type': 'event_callback', 'team_id': 'TXXX', 'event': {'type': 'app_home_opened', 'user': 'UXXX3', 'channel': 'DXXX', 'tab': 'home'}}, ['UXXX3']),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX1'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, ['UXXX1']),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX2'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, ['UXXX2']),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX3'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, [])
]

@pytest.fixture
def settings() -> threadvault.configuration.Settings:

    return threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX1,UXXX2'})

@pytest.mark.parametrize(('user', 'role'), USERS_CLASSIFIED)
def test_permission_user_role(
    settings: threadvault.configuration.Settings,
    user: str,
    role: threadvault.slack.permission.Role
) -> None:

    assert threadvault.slack.permission.role(settings, user) == role

@pytest.mark.parametrize(('body', 'users'), REQUESTS_PERMITTED)
def test_permission_request_restriction(
    slack: slack_sdk.web.WebClient,
    settings: threadvault.configuration.Settings,
    body: dict[str, typing.Any],
    users: list[str]
) -> None:

    reached = []

    def listen(
        ack: slack_bolt.Ack,
        context: slack_bolt.BoltContext
    ) -> None:

        ack()
        reached.append(context.user_id)

    application = slack_bolt.App(client = slack, process_before_response = True)
    application.use(threadvault.slack.permission.restrict(settings))
    application.event('app_home_opened')(listen)
    application.action('xxx')(listen)

    assert application.dispatch(slack_bolt.BoltRequest(body = body, mode = 'socket_mode')).status == 200
    assert reached == users
