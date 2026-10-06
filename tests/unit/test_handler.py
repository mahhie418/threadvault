import collections.abc
import datetime
import os
import pathlib
import typing

import pytest
import slack_bolt
import slack_sdk

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

TOKENS_SAVED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx', access_expiry = NOW + datetime.timedelta(hours = 8), refresh_token = 'ghr_xxx', refresh_expiry = NOW + datetime.timedelta(days = 184))

TABS_OPENED = [('home', 1), ('messages', 0)]
VIEWERS_HOME = [('UXXX1', 'owner'), ('UXXX2', 'admin'), ('UXXX3', 'member')]

@pytest.fixture
def application(
    slack: slack_sdk.web.WebClient,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> slack_bolt.App:

    application = slack_bolt.App(client = slack, process_before_response = True)
    threadvault.slack.handler.register(application, threadvault.configuration.load({'THREADVAULT_OWNER_ID': 'UXXX1', 'THREADVAULT_ADMIN_IDS': 'UXXX2', 'THREADVAULT_LANGUAGE_DISPLAY': 'ja'}), database, manager)

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
