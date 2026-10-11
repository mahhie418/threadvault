import datetime
import json
import typing

import pytest

import threadvault.customisation
import threadvault.github.oauth
import threadvault.journal
import threadvault.slack.permission
import threadvault.slack.view

CODE = threadvault.github.oauth.Code(device_code = 'xxx', user_code = 'XXXX-XXXX', verification_uri = 'https://github.com/login/device', interval = 5)
RUN_SUCCEEDED = threadvault.journal.Run(completion = datetime.datetime(2026, 10, 8, 15, 0, tzinfo = datetime.UTC), repository = 'xxx/xxx1', commit = '0123456789abcdef0123456789abcdef01234567', reason = None)
RUN_FAILED = threadvault.journal.Run(completion = datetime.datetime(2026, 10, 8, 15, 0, tzinfo = datetime.UTC), repository = 'xxx/xxx1', commit = None, reason = 'xxx')
TIME_PLANNED = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)

STATES_HOME = [
    ({'github': 'connected', 'destination': 'xxx/xxx', 'last': RUN_SUCCEEDED, 'planned': TIME_PLANNED, 'role': 'owner', 'language': 'ja'}, ['*GitHub*\n連携済み', '*保存先*\n<https://github.com/xxx/xxx|xxx/xxx>', '*前回のバックアップ*\n<!date^1791471600^{date_short} {time}|2026-10-08 15:00 UTC> に成功しました\n<https://github.com/xxx/xxx1/commit/0123456789abcdef0123456789abcdef01234567|0123456>', '*次回のバックアップ*\n<!date^1791558000^{date_short} {time}|2026-10-09 15:00 UTC>']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'last': RUN_SUCCEEDED, 'planned': TIME_PLANNED, 'role': 'member', 'language': 'en'}, ['*GitHub*\nConnected', '*Last backup*\nSucceeded at <!date^1791471600^{date_short} {time}|2026-10-08 15:00 UTC>', '*Next backup*\n<!date^1791558000^{date_short} {time}|2026-10-09 15:00 UTC>']),
    ({'github': 'disconnected', 'destination': None, 'last': None, 'planned': None, 'role': 'admin', 'language': 'en'}, ['*GitHub*\nNot connected', '*Destination*\nNot chosen', '*Last backup*\nNone yet', '*Next backup*\nNot scheduled']),
    ({'github': 'expired', 'destination': None, 'last': RUN_FAILED, 'planned': None, 'role': 'admin', 'language': 'en'}, ['*GitHub*\nNeeds reconnecting', '*Destination*\nNot chosen', '*Last backup*\nFailed at <!date^1791471600^{date_short} {time}|2026-10-08 15:00 UTC>\nxxx', '*Next backup*\nNot scheduled']),
    ({'github': 'uninstalled', 'destination': None, 'last': None, 'planned': None, 'role': 'admin', 'language': 'en'}, ['*GitHub*\nConnected', '*Destination*\nNot chosen', '*Last backup*\nNone yet', '*Next backup*\nNot scheduled']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'last': RUN_FAILED, 'planned': None, 'role': 'member', 'language': 'ja'}, ['*GitHub*\n連携済み', '*前回のバックアップ*\n<!date^1791471600^{date_short} {time}|2026-10-08 15:00 UTC> に失敗しました', '*次回のバックアップ*\n予定なし'])
]

ROLES_MESSAGE = [
    ('owner', ['You are the owner.']),
    ('operator', ['You are an admin with permission to operate the app.']),
    ('admin', ['You are an admin without permission to operate the app.']),
    ('member', [])
]

VIEWERS_MESSAGE = [
    ({'github': 'connected', 'role': 'owner'}, [(threadvault.slack.view.DISCONNECTION_ACTION, 'Disconnect GitHub', True), (threadvault.slack.view.DESTINATION_ACTION, 'Choose destination', False), (threadvault.slack.view.CREATION_ACTION, 'Create repository', False), (threadvault.slack.view.SETTINGS_ACTION, 'Settings', False), (threadvault.slack.view.PERMISSIONS_ACTION, 'Admin permissions', False), (threadvault.slack.view.TRANSFER_ACTION, 'Transfer ownership', False)]),
    ({'github': 'connected', 'role': 'operator'}, [(threadvault.slack.view.DISCONNECTION_ACTION, 'Disconnect GitHub', True), (threadvault.slack.view.DESTINATION_ACTION, 'Choose destination', False), (threadvault.slack.view.CREATION_ACTION, 'Create repository', False), (threadvault.slack.view.SETTINGS_ACTION, 'Settings', False)]),
    ({'github': 'connected', 'role': 'admin'}, []),
    ({'github': 'disconnected', 'role': 'owner'}, [(threadvault.slack.view.CONNECTION_ACTION, 'Connect GitHub', False), (threadvault.slack.view.SETTINGS_ACTION, 'Settings', False), (threadvault.slack.view.PERMISSIONS_ACTION, 'Admin permissions', False), (threadvault.slack.view.TRANSFER_ACTION, 'Transfer ownership', False)]),
    ({'github': 'disconnected', 'role': 'operator'}, [(threadvault.slack.view.CONNECTION_ACTION, 'Connect GitHub', False), (threadvault.slack.view.SETTINGS_ACTION, 'Settings', False)]),
    ({'github': 'disconnected', 'role': 'member'}, []),
    ({'github': 'expired', 'role': 'operator'}, [(threadvault.slack.view.CONNECTION_ACTION, 'Reconnect GitHub', False), (threadvault.slack.view.SETTINGS_ACTION, 'Settings', False)]),
    ({'github': 'expired', 'role': 'admin'}, []),
    ({'github': 'uninstalled', 'role': 'operator'}, [(threadvault.slack.view.DISCONNECTION_ACTION, 'Disconnect GitHub', True), (threadvault.slack.view.SETTINGS_ACTION, 'Settings', False)])
]

VIEWERS_INSTALLATION = [
    ({'github': 'connected', 'role': 'owner'}, []),
    ({'github': 'disconnected', 'role': 'owner'}, []),
    ({'github': 'expired', 'role': 'owner'}, []),
    ({'github': 'uninstalled', 'role': 'owner'}, ['*GitHub App*\nNot installed yet. <https://github.com/apps/xxx1/installations/new|Install it> on the account or organisation that will hold the vault.']),
    ({'github': 'uninstalled', 'role': 'operator'}, ['*GitHub App*\nNot installed yet. <https://github.com/apps/xxx1/installations/new|Install it> on the account or organisation that will hold the vault.']),
    ({'github': 'uninstalled', 'role': 'admin'}, []),
    ({'github': 'uninstalled', 'role': 'member'}, [])
]

VIEWERS_BACKUP = [
    ({'github': 'connected', 'destination': 'xxx/xxx', 'running': False, 'role': 'owner'}, [(threadvault.slack.view.BACKUP_ACTION, 'Back up now', False), (threadvault.slack.view.RESYNCHRONISATION_ACTION, 'Resynchronise everything', True)], ['You are the owner.']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'running': False, 'role': 'operator'}, [(threadvault.slack.view.BACKUP_ACTION, 'Back up now', False), (threadvault.slack.view.RESYNCHRONISATION_ACTION, 'Resynchronise everything', True)], ['You are an admin with permission to operate the app.']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'running': False, 'role': 'admin'}, [], ['You are an admin without permission to operate the app.']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'running': True, 'role': 'owner'}, [], ['You are the owner.', 'Backing up the workspace…']),
    ({'github': 'connected', 'destination': 'xxx/xxx', 'running': True, 'role': 'member'}, [], ['Backing up the workspace…']),
    ({'github': 'connected', 'destination': None, 'running': False, 'role': 'owner'}, [], ['You are the owner.']),
    ({'github': 'uninstalled', 'destination': 'xxx/xxx', 'running': False, 'role': 'owner'}, [], ['You are the owner.'])
]

DESTINATIONS_CURRENT = [
    (None, []),
    ('xxx/xxx', ['xxx/xxx'])
]

OUTCOMES_DESTINATION = [
    ('check', '', 'Checking xxx/xxx…'),
    ('success', '', 'Backups now go to xxx/xxx.'),
    ('absence', '', 'xxx/xxx was not found, or the GitHub App cannot access it.'),
    ('publicity', '', 'xxx/xxx is public. Backups go only into private repositories.'),
    ('failure', 'xxx', 'The repository could not be checked: xxx')
]

OUTCOMES_CREATION = [
    ('check', '', 'Creating xxx/xxx…'),
    ('success', '', 'Created xxx/xxx. Backups now go there.'),
    ('failure', 'xxx', 'The repository could not be created: xxx')
]

ACCOUNTS_CREATION = [
    (None, ['Listing the accounts that have the GitHub App…']),
    ([], ['The GitHub App is not installed on any account yet. Install it first.'])
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

SETTINGS_STATUS = [
    (threadvault.customisation.Settings(), [['enabled'], '00:00', 'UTC', 'joined', [], ['enabled'], ['enabled'], '20', 'en']),
    (threadvault.customisation.Settings(schedule_enabled = False, schedule_time = '12:00', workspace_timezone = 'Asia/Tokyo', channel_mode = 'selected', channels_selected = ('CXXX1', 'CXXX2'), channels_joined = False, attachments_enabled = False, attachment_size_maximum = 50, markdown_language = 'ja'), [[], '12:00', 'Asia/Tokyo', 'selected', ['CXXX1', 'CXXX2'], [], [], '50', 'ja'])
]

@pytest.mark.parametrize(('state', 'texts'), STATES_HOME)
def test_view_home_status(
    state: dict[str, typing.Any],
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(**state, running = False, slug = 'xxx')

    assert view['type'] == 'home'
    assert [field['text'] for block in view['blocks'] if 'fields' in block for field in block['fields']] == texts

@pytest.mark.parametrize(('role', 'texts'), ROLES_MESSAGE)
def test_view_home_role(
    role: threadvault.slack.permission.Role,
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(github = 'disconnected', destination = None, running = False, last = None, planned = None, role = role, slug = 'xxx', language = 'en')

    assert [element['text'] for block in view['blocks'] if block['type'] == 'context' for element in block['elements']] == texts

@pytest.mark.parametrize(('state', 'buttons'), VIEWERS_MESSAGE)
def test_view_home_connection(
    state: dict[str, typing.Any],
    buttons: list[tuple[str, str, bool]]
) -> None:

    view = threadvault.slack.view.home(**state, destination = None, running = False, last = None, planned = None, slug = 'xxx', language = 'en')

    assert [(element['action_id'], element['text']['text'], 'confirm' in element) for block in view['blocks'] if block['type'] == 'actions' for element in block['elements']] == buttons

@pytest.mark.parametrize(('state', 'buttons', 'notes'), VIEWERS_BACKUP)
def test_view_home_backup(
    state: dict[str, typing.Any],
    buttons: list[tuple[str, str, bool]],
    notes: list[str]
) -> None:

    view = threadvault.slack.view.home(**state, last = None, planned = None, slug = 'xxx', language = 'en')

    assert [(element['action_id'], element['text']['text'], 'confirm' in element) for block in view['blocks'] if block['type'] == 'actions' for element in block['elements'] if element['action_id'] in (threadvault.slack.view.BACKUP_ACTION, threadvault.slack.view.RESYNCHRONISATION_ACTION)] == buttons
    assert [element['text'] for block in view['blocks'] if block['type'] == 'context' for element in block['elements']] == notes

@pytest.mark.parametrize(('state', 'texts'), VIEWERS_INSTALLATION)
def test_view_home_installation(
    state: dict[str, typing.Any],
    texts: list[str]
) -> None:

    view = threadvault.slack.view.home(**state, destination = None, running = False, last = None, planned = None, slug = 'xxx1', language = 'en')

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

@pytest.mark.parametrize(('current', 'values'), DESTINATIONS_CURRENT)
def test_view_destination_menu(
    current: str | None,
    values: list[str]
) -> None:

    view = threadvault.slack.view.offer(current = current, language = 'en')
    menu = view['blocks'][0]['element']

    assert (view['callback_id'], menu['action_id'], menu['min_query_length']) == (threadvault.slack.view.DESTINATION_CALLBACK, threadvault.slack.view.REPOSITORY_ACTION, 0)
    assert ([menu['initial_option']['value']] if 'initial_option' in menu else []) == values

def test_view_destination_option() -> None:

    names = [f'xxx/{'x' * 80}', *(f'xxx/xxx{index}' for index in range(150))]
    options = threadvault.slack.view.suggest(names)

    assert [option['value'] for option in options] == names[:100]
    assert options[0]['text']['text'] == f'xxx/{'x' * 70}…'

@pytest.mark.parametrize(('outcome', 'message', 'text'), OUTCOMES_DESTINATION)
def test_view_destination_result(
    outcome: threadvault.slack.view.DestinationOutcome,
    message: str,
    text: str
) -> None:

    view = threadvault.slack.view.settle(repository = 'xxx/xxx', outcome = outcome, language = 'en', message = message)

    assert view['type'] == 'modal'
    assert [block['text']['text'] for block in view['blocks']] == [text]

@pytest.mark.parametrize(('accounts', 'texts'), ACCOUNTS_CREATION)
def test_view_creation_progress(
    accounts: list[str] | None,
    texts: list[str]
) -> None:

    view = threadvault.slack.view.propose(accounts = accounts, language = 'en')

    assert 'submit' not in view
    assert [block['text']['text'] for block in view['blocks']] == texts

def test_view_creation_form() -> None:

    view = threadvault.slack.view.propose(accounts = ['xxx1', 'xxx2'], language = 'en')
    account, name = (block['element'] for block in view['blocks'])

    assert view['callback_id'] == threadvault.slack.view.CREATION_CALLBACK
    assert (account['action_id'], [option['value'] for option in account['options']], account['initial_option']['value']) == (threadvault.slack.view.ACCOUNT_INPUT, ['xxx1', 'xxx2'], 'xxx1')
    assert (name['action_id'], name['max_length']) == (threadvault.slack.view.NAME_INPUT, 100)

@pytest.mark.parametrize(('outcome', 'message', 'text'), OUTCOMES_CREATION)
def test_view_creation_result(
    outcome: threadvault.slack.view.CreationOutcome,
    message: str,
    text: str
) -> None:

    view = threadvault.slack.view.establish(repository = 'xxx/xxx', outcome = outcome, language = 'en', message = message)

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

@pytest.mark.parametrize(('settings', 'values'), SETTINGS_STATUS)
def test_view_settings_configuration(
    settings: threadvault.customisation.Settings,
    values: list[typing.Any]
) -> None:

    view = threadvault.slack.view.configure(workspace = settings, language = 'en')
    elements: dict[str, dict[str, typing.Any]] = {block['block_id']: block['element'] for block in view['blocks']}

    assert view['callback_id'] == threadvault.slack.view.SETTINGS_CALLBACK
    assert [[option['value'] for option in elements[threadvault.slack.view.SCHEDULE_INPUT].get('initial_options', [])], elements[threadvault.slack.view.TIME_INPUT]['initial_time'], elements[threadvault.slack.view.TIMEZONE_ACTION]['initial_option']['value'], elements[threadvault.slack.view.MODE_INPUT]['initial_option']['value'], elements[threadvault.slack.view.CHANNELS_INPUT].get('initial_conversations', []), [option['value'] for option in elements[threadvault.slack.view.JOINING_INPUT].get('initial_options', [])], [option['value'] for option in elements[threadvault.slack.view.ATTACHMENTS_INPUT].get('initial_options', [])], elements[threadvault.slack.view.SIZE_INPUT]['initial_value'], elements[threadvault.slack.view.LANGUAGE_INPUT]['initial_option']['value']] == values
