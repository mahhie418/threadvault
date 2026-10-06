import collections.abc
import os
import pathlib
import typing

import pytest
import slack_bolt
import slack_sdk

import threadvault.configuration
import threadvault.customisation
import threadvault.slack.permission
import threadvault.storage

WORKSPACE = threadvault.customisation.Settings(admins_allowed = ('UXXX2', 'UXXX4'))

USERS_CLASSIFIED = [('UXXX1', 'owner'), ('UXXX2', 'operator'), ('UXXX3', 'admin'), ('UXXX4', 'member')]

REQUESTS_PERMITTED = [
    ({'type': 'event_callback', 'team_id': 'TXXX', 'event': {'type': 'app_home_opened', 'user': 'UXXX4', 'channel': 'DXXX', 'tab': 'home'}}, frozenset({'owner'}), ['UXXX4']),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX1'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, frozenset({'owner', 'operator'}), ['UXXX1']),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX2'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, frozenset({'owner', 'operator'}), ['UXXX2']),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX3'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, frozenset({'owner', 'operator'}), []),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX4'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, frozenset({'owner', 'operator'}), []),
    ({'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': 'UXXX2'}, 'actions': [{'type': 'button', 'action_id': 'xxx'}]}, frozenset({'owner'}), [])
]

@pytest.fixture
def settings() -> threadvault.configuration.Settings:

    return threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX1,UXXX2,UXXX3'})

@pytest.fixture
def store(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.customisation.SettingsIO]:

    database = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE)))
    opening = threadvault.customisation.SettingsIO(database)
    opening.save('TXXX', WORKSPACE, update_user = 'UXXX1'); yield opening
    database.close()

@pytest.mark.parametrize(('user', 'role'), USERS_CLASSIFIED)
def test_permission_user_role(
    settings: threadvault.configuration.Settings,
    user: str,
    role: threadvault.slack.permission.Role
) -> None:

    assert threadvault.slack.permission.role(settings, WORKSPACE, user) == role

@pytest.mark.parametrize(('body', 'roles', 'users'), REQUESTS_PERMITTED)
def test_permission_request_restriction(
    slack: slack_sdk.web.WebClient,
    settings: threadvault.configuration.Settings,
    store: threadvault.customisation.SettingsIO,
    body: dict[str, typing.Any],
    roles: frozenset[threadvault.slack.permission.Role],
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
    application.use(threadvault.slack.permission.restrict(settings, store, roles))
    application.event('app_home_opened')(listen)
    application.action('xxx')(listen)

    assert application.dispatch(slack_bolt.BoltRequest(body = body, mode = 'socket_mode')).status == 200
    assert reached == users
