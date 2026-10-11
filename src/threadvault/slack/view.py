"""Views of the Slack app: the App Home and its modals."""

import datetime
import json
import typing

import threadvault.configuration
import threadvault.customisation
import threadvault.github.oauth
import threadvault.journal
import threadvault.localisation
import threadvault.slack.permission

type GitHubState = typing.Literal['connected', 'disconnected', 'expired', 'uninstalled']
type DestinationOutcome = typing.Literal['check', 'success', 'absence', 'publicity', 'failure']
type CreationOutcome = typing.Literal['check', 'success', 'failure']

BACKUP_ACTION = 'backup_action'
RESYNCHRONISATION_ACTION = 'resynchronisation_action'
CONNECTION_ACTION = 'connection_action'
DISCONNECTION_ACTION = 'disconnection_action'
DESTINATION_ACTION = 'destination_action'
DESTINATION_CALLBACK = 'destination_callback'
CREATION_ACTION = 'creation_action'
CREATION_CALLBACK = 'creation_callback'
PERMISSIONS_ACTION = 'permissions_action'
PERMISSIONS_CALLBACK = 'permissions_callback'
PERMISSIONS_CONFIRMATION = 'permissions_confirmation'
REPOSITORY_ACTION = 'repository_action'
TRANSFER_ACTION = 'transfer_action'
TRANSFER_CALLBACK = 'transfer_callback'
TRANSFER_CONFIRMATION = 'transfer_confirmation'
SETTINGS_ACTION = 'settings_action'
SETTINGS_CALLBACK = 'settings_callback'
TIMEZONE_ACTION = 'timezone_action'

ACCOUNT_INPUT = 'account_input'
ADMINS_INPUT = 'admins_input'
SUCCESSOR_INPUT = 'successor_input'
NAME_INPUT = 'name_input'
SCHEDULE_INPUT = 'schedule_input'
TIME_INPUT = 'time_input'
MODE_INPUT = 'mode_input'
CHANNELS_INPUT = 'channels_input'
JOINING_INPUT = 'joining_input'
ATTACHMENTS_INPUT = 'attachments_input'
SIZE_INPUT = 'size_input'
LANGUAGE_INPUT = 'language_input'

_OPTION_LIMIT = 100
_DISPLAY_LIMIT = 75
_CHECKBOX_LIMIT = 10
_NAME_LIMIT = 100

def home(
    *,
    github: GitHubState,
    destination: str | None,
    running: bool,
    last: threadvault.journal.Run | None,
    planned: datetime.datetime | None,
    role: threadvault.slack.permission.Role,
    slug: str,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows the state of the backup.

    Everyone sees when the last backup ended and whether it succeeded. The
    owner and the admins also see the commit that it left in the vault, or
    why it failed. Everyone also sees when the daily backup runs next.

    While a backup is running, everyone sees so. Otherwise, while GitHub is
    connected and the destination is chosen, the owner and the admins allowed
    to operate the app see a button that backs up the workspace at once, and
    one that resynchronises the whole workspace once they confirm it.

    The owner and the admins also see the destination and their own role.
    The owner and the admins allowed to operate the app see a button that
    connects GitHub, connects it again once the connection has stopped
    working, or disconnects it, buttons that choose or create the destination
    while GitHub is connected, a button that opens the settings, and a link
    to install the GitHub App while it has no installation. The owner also
    sees buttons that choose the admins allowed to operate the app and that
    transfer the ownership to an admin.

    Args:
        github: State of the connection to GitHub: disconnected, expired when
                the tokens no longer work, uninstalled when the GitHub App has
                no installation that the connected account can access, or
                connected.
        destination: Repository of the vault, as owner/name, or None while none is chosen.
        running: Whether a backup is running.
        last: The backup that ended last, or None before the first one ends.
        planned: Time of the next daily backup, or None while none is planned.
        role: Role of the viewer.
        slug: URL slug of the GitHub App.
        language: Language of the viewer.

    Returns:
        The view, as views.publish takes it.
    """

    match github:

        case 'disconnected': connection = threadvault.localisation.translate('home.github.disconnected', language)
        case 'expired': connection = threadvault.localisation.translate('home.github.expired', language)
        case _: connection = threadvault.localisation.translate('home.github.connected', language)

    fields = [(threadvault.localisation.translate('home.github', language), connection)]
    blocks = []

    if role != 'member':

        fields.append((threadvault.localisation.translate('home.destination', language), f'<https://github.com/{destination}|{destination}>' if destination else threadvault.localisation.translate('home.destination.missing', language)))
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': threadvault.localisation.translate(f'home.role.{role}', language)}]})

    fields.append((threadvault.localisation.translate('home.backup.last', language), _report(last = last, role = role, language = language)))
    fields.append((threadvault.localisation.translate('home.schedule', language), _date(planned) if planned else threadvault.localisation.translate('home.schedule.missing', language)))
    blocks.append({'type': 'section', 'fields': [_text(title, text) for title, text in fields]})

    if running: blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': threadvault.localisation.translate('home.backup.running', language)}]})
    elif role in ('owner', 'operator') and github == 'connected' and destination: blocks.append({'type': 'actions', 'elements': [{'type': 'button', 'action_id': BACKUP_ACTION, 'style': 'primary', 'text': _plain(threadvault.localisation.translate('home.backup', language))}, {'type': 'button', 'action_id': RESYNCHRONISATION_ACTION, 'text': _plain(threadvault.localisation.translate('home.resynchronisation', language)), 'confirm': _confirmation('resynchronisation', 'primary', language)}]})

    buttons = [_button(github = github, language = language)]

    if github == 'connected': buttons.extend({'type': 'button', 'action_id': action, 'text': _plain(threadvault.localisation.translate(key, language))} for action, key in ((DESTINATION_ACTION, 'home.destination.choice'), (CREATION_ACTION, 'home.destination.creation')))

    buttons.append({'type': 'button', 'action_id': SETTINGS_ACTION, 'text': _plain(threadvault.localisation.translate('home.settings', language))})

    if role in ('owner', 'operator'): blocks.append({'type': 'actions', 'elements': buttons})
    if role in ('owner', 'operator') and github == 'uninstalled': blocks.append({'type': 'section', 'text': _text(threadvault.localisation.translate('home.installation', language), threadvault.localisation.translate('home.installation.missing', language, url = f'https://github.com/apps/{slug}/installations/new'))})
    if role == 'owner': blocks.append({'type': 'actions', 'elements': [{'type': 'button', 'action_id': action, 'text': _plain(threadvault.localisation.translate(key, language))} for action, key in ((PERMISSIONS_ACTION, 'home.permissions'), (TRANSFER_ACTION, 'home.transfer'))]})

    return {'type': 'home', 'blocks': blocks}

def connect(
    *,
    code: threadvault.github.oauth.Code | None,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that connects GitHub, while GitHub is asked for a code and while the admin enters it.

    Args:
        code: Code for the admin to enter on GitHub, or None until GitHub gives one.
        language: Language of the admin.

    Returns:
        The view, as views.open and views.update take it.
    """

    text = threadvault.localisation.translate('connection.code', language, code = code.user_code, url = code.verification_uri) if code else threadvault.localisation.translate('connection.request', language)

    return _modal(threadvault.localisation.translate('connection.title', language), text, language)

def respond(
    *,
    error: threadvault.github.oauth.OAuthError | None,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that connects GitHub, once GitHub is connected or the device flow has failed.

    Args:
        error: Why GitHub was not connected, or None when it was.
        language: Language of the admin.

    Returns:
        The view, as views.update takes it.
    """

    match error:

        case None: text = threadvault.localisation.translate('connection.success', language)
        case threadvault.github.oauth.OAuthError(reason = 'access_denied'): text = threadvault.localisation.translate('connection.denial', language)
        case threadvault.github.oauth.OAuthError(reason = 'expired_token'): text = threadvault.localisation.translate('connection.expiry', language)
        case _: text = threadvault.localisation.translate('connection.failure', language, message = str(error))

    return _modal(threadvault.localisation.translate('connection.title', language), text, language)

def offer(
    *,
    current: str | None,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that chooses the destination among the private repositories that the GitHub App can access.

    Args:
        current: Repository of the vault, as owner/name, or None while none is chosen.
        language: Language of the admin.

    Returns:
        The view, as views.open takes it.
    """

    menu: dict[str, typing.Any] = {'type': 'external_select', 'action_id': REPOSITORY_ACTION, 'min_query_length': 0, 'placeholder': _plain(threadvault.localisation.translate('destination.placeholder', language))}

    if current: menu['initial_option'] = _option(current)

    block = {'type': 'input', 'block_id': REPOSITORY_ACTION, 'label': _plain(threadvault.localisation.translate('destination.repository', language)), 'hint': _plain(threadvault.localisation.translate('destination.hint', language)), 'element': menu}

    return {'type': 'modal', 'callback_id': DESTINATION_CALLBACK, 'title': _plain(threadvault.localisation.translate('destination.title', language)), 'submit': _plain(threadvault.localisation.translate('destination.submit', language)), 'close': _plain(threadvault.localisation.translate('destination.close', language)), 'blocks': [block]}

def suggest(
    names: list[str]
) -> list[dict[str, typing.Any]]:

    """Builds the options of a menu, as many as Slack takes.

    Args:
        names: Repositories as owner/name, GitHub accounts, or time zones.

    Returns:
        The options, as an options response takes them.
    """

    return [_option(name) for name in names[:_OPTION_LIMIT]]

def settle(
    *,
    repository: str,
    outcome: DestinationOutcome,
    language: threadvault.configuration.Language,
    message: str = ''
) -> dict[str, typing.Any]:

    """Builds the modal that chooses the destination, once a repository is submitted.

    Args:
        repository: The repository, as owner/name.
        outcome: Where the check of the repository stands: check while it
                 runs, success once the repository is the destination,
                 absence when the GitHub App cannot find it, publicity when
                 it is public, or failure when it could not be checked.
        language: Language of the admin.
        message: Why the repository could not be checked.

    Returns:
        The view, as an update response and views.update take it.
    """

    return _modal(threadvault.localisation.translate('destination.title', language), threadvault.localisation.translate(f'destination.{outcome}', language, repository = repository, message = message), language)

def propose(
    *,
    accounts: list[str] | None,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that creates a private repository for the destination, while the accounts are listed and once they are.

    Args:
        accounts: Accounts that have the GitHub App, as GitHub names them,
                  or None until GitHub lists them.
        language: Language of the admin.

    Returns:
        The view, as views.open and views.update take it.
    """

    title = threadvault.localisation.translate('creation.title', language)

    if accounts is None: return _modal(title, threadvault.localisation.translate('creation.request', language), language)
    if not accounts: return _modal(title, threadvault.localisation.translate('creation.absence', language), language)

    account = {'type': 'input', 'block_id': ACCOUNT_INPUT, 'label': _plain(threadvault.localisation.translate('creation.account', language)), 'element': {'type': 'static_select', 'action_id': ACCOUNT_INPUT, 'options': suggest(accounts), 'initial_option': _option(accounts[0])}}
    name = {'type': 'input', 'block_id': NAME_INPUT, 'label': _plain(threadvault.localisation.translate('creation.name', language)), 'hint': _plain(threadvault.localisation.translate('creation.hint', language)), 'element': {'type': 'plain_text_input', 'action_id': NAME_INPUT, 'max_length': _NAME_LIMIT}}

    return {'type': 'modal', 'callback_id': CREATION_CALLBACK, 'title': _plain(title), 'submit': _plain(threadvault.localisation.translate('creation.submit', language)), 'close': _plain(threadvault.localisation.translate('creation.close', language)), 'blocks': [account, name]}

def establish(
    *,
    repository: str,
    outcome: CreationOutcome,
    language: threadvault.configuration.Language,
    message: str = ''
) -> dict[str, typing.Any]:

    """Builds the modal that creates a private repository for the destination, once it is submitted.

    Args:
        repository: The repository, as owner/name.
        outcome: Where the creation stands: check while it runs, success
                 once the repository is the destination, or failure.
        language: Language of the admin.
        message: Why the repository could not be created.

    Returns:
        The view, as an update response and views.update take it.
    """

    return _modal(threadvault.localisation.translate('creation.title', language), threadvault.localisation.translate(f'creation.{outcome}', language, repository = repository, message = message), language)

def permit(
    *,
    admins: list[str],
    allowed: tuple[str, ...],
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which the owner chooses the admins allowed to operate the app.

    Slack shows at most 10 checkboxes together, so the admins come in groups of 10.

    Args:
        admins: Slack user IDs of the admins other than the owner.
        allowed: Slack user IDs of the admins allowed now.
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    title = threadvault.localisation.translate('permissions.title', language)

    if not admins: return _modal(title, threadvault.localisation.translate('permissions.absence', language), language)

    blocks: list[dict[str, typing.Any]] = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': threadvault.localisation.translate('permissions.description', language)}}]

    for index in range(0, len(admins), _CHECKBOX_LIMIT):

        group = admins[index:index + _CHECKBOX_LIMIT]
        blocks.append({'type': 'input', 'block_id': f'{ADMINS_INPUT}{index // _CHECKBOX_LIMIT}', 'optional': True, 'label': _plain(threadvault.localisation.translate('permissions.label', language)), 'element': _checkbox(ADMINS_INPUT, [_choice(admin) for admin in group], allowed)})

    return {'type': 'modal', 'callback_id': PERMISSIONS_CALLBACK, 'title': _plain(title), 'submit': _plain(threadvault.localisation.translate('permissions.submit', language)), 'close': _plain(threadvault.localisation.translate('permissions.close', language)), 'blocks': blocks}

def review(
    *,
    granted: list[str],
    revoked: list[str],
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the view that asks the owner to confirm changes to the admin permissions.

    The changes travel with the view, so that confirming it applies them.

    Args:
        granted: Slack user IDs of the admins to allow.
        revoked: Slack user IDs of the admins whose permission to withdraw.
        language: Language of the owner.

    Returns:
        The view, as a push response takes it.
    """

    lines = [threadvault.localisation.translate('permissions.grant', language, user = user) for user in granted] + [threadvault.localisation.translate('permissions.revocation', language, user = user) for user in revoked]
    text = '\n'.join([threadvault.localisation.translate('permissions.question', language), *(f'• {line}' for line in lines)])

    return {'type': 'modal', 'callback_id': PERMISSIONS_CONFIRMATION, 'private_metadata': json.dumps({'granted': granted, 'revoked': revoked}), 'title': _plain(threadvault.localisation.translate('permissions.title', language)), 'submit': _plain(threadvault.localisation.translate('permissions.confirm', language)), 'close': _plain(threadvault.localisation.translate('permissions.back', language)), 'blocks': [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}]}

def cede(
    *,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which the owner chooses the admin who becomes the owner.

    Args:
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    blocks = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': threadvault.localisation.translate('transfer.description', language)}}, {'type': 'input', 'block_id': SUCCESSOR_INPUT, 'label': _plain(threadvault.localisation.translate('transfer.label', language)), 'element': {'type': 'users_select', 'action_id': SUCCESSOR_INPUT}}]

    return {'type': 'modal', 'callback_id': TRANSFER_CALLBACK, 'title': _plain(threadvault.localisation.translate('transfer.title', language)), 'submit': _plain(threadvault.localisation.translate('transfer.submit', language)), 'close': _plain(threadvault.localisation.translate('transfer.close', language)), 'blocks': blocks}

def nominate(
    *,
    successor: str,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the view that asks the owner to confirm the transfer of the ownership.

    The successor travels with the view, so that confirming it transfers the ownership to them.

    Args:
        successor: Slack user ID of the admin who becomes the owner.
        language: Language of the owner.

    Returns:
        The view, as a push response takes it.
    """

    return {'type': 'modal', 'callback_id': TRANSFER_CONFIRMATION, 'private_metadata': successor, 'title': _plain(threadvault.localisation.translate('transfer.title', language)), 'submit': _plain(threadvault.localisation.translate('transfer.confirm', language)), 'close': _plain(threadvault.localisation.translate('transfer.back', language)), 'blocks': [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': threadvault.localisation.translate('transfer.question', language, user = successor)}}]}

def configure(
    *,
    workspace: threadvault.customisation.Settings,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that changes the settings of the workspace, showing their current values.

    The daily backup runs at its time in its time zone, which the Markdown
    follows too from the next backup. Backups cover every channel that the
    bot is in, or only the chosen ones among them, which the bot first joins
    when they are public and joining is on, and save the attached files up
    to a size, or none. The Markdown follows the chosen language too from
    the next backup.

    Args:
        workspace: Settings of the workspace to show.
        language: Language of the admin.

    Returns:
        The view, as views.open takes it.
    """

    modes = {mode: {'text': _plain(threadvault.localisation.translate(f'settings.mode.{mode}', language)), 'value': mode} for mode in ('joined', 'selected')}
    channels: dict[str, typing.Any] = {'type': 'multi_conversations_select', 'action_id': CHANNELS_INPUT, 'filter': {'include': ['public', 'private'], 'exclude_external_shared_channels': True}}

    if workspace.channels_selected: channels['initial_conversations'] = list(workspace.channels_selected)

    languages = {code: {'text': _plain(threadvault.localisation.translate(f'settings.language.{code}', language)), 'value': code} for code in ('en', 'ja')}

    blocks = [
        {'type': 'input', 'block_id': SCHEDULE_INPUT, 'optional': True, 'label': _plain(threadvault.localisation.translate('settings.schedule', language)), 'element': _checkbox(SCHEDULE_INPUT, [{'text': _plain(threadvault.localisation.translate('settings.schedule.enabled', language)), 'value': 'enabled'}], ('enabled',) if workspace.schedule_enabled else ())},
        {'type': 'input', 'block_id': TIME_INPUT, 'label': _plain(threadvault.localisation.translate('settings.time', language)), 'element': {'type': 'timepicker', 'action_id': TIME_INPUT, 'initial_time': workspace.schedule_time}},
        {'type': 'input', 'block_id': TIMEZONE_ACTION, 'label': _plain(threadvault.localisation.translate('settings.timezone', language)), 'hint': _plain(threadvault.localisation.translate('settings.timezone.hint', language)), 'element': {'type': 'external_select', 'action_id': TIMEZONE_ACTION, 'min_query_length': 1, 'initial_option': _option(workspace.workspace_timezone)}},
        {'type': 'input', 'block_id': MODE_INPUT, 'label': _plain(threadvault.localisation.translate('settings.mode', language)), 'element': {'type': 'radio_buttons', 'action_id': MODE_INPUT, 'options': list(modes.values()), 'initial_option': modes[workspace.channel_mode]}},
        {'type': 'input', 'block_id': CHANNELS_INPUT, 'optional': True, 'label': _plain(threadvault.localisation.translate('settings.channels', language)), 'hint': _plain(threadvault.localisation.translate('settings.channels.hint', language)), 'element': channels},
        {'type': 'input', 'block_id': JOINING_INPUT, 'optional': True, 'label': _plain(threadvault.localisation.translate('settings.joining', language)), 'hint': _plain(threadvault.localisation.translate('settings.joining.hint', language)), 'element': _checkbox(JOINING_INPUT, [{'text': _plain(threadvault.localisation.translate('settings.joining.enabled', language)), 'value': 'enabled'}], ('enabled',) if workspace.channels_joined else ())},
        {'type': 'input', 'block_id': ATTACHMENTS_INPUT, 'optional': True, 'label': _plain(threadvault.localisation.translate('settings.attachments', language)), 'element': _checkbox(ATTACHMENTS_INPUT, [{'text': _plain(threadvault.localisation.translate('settings.attachments.enabled', language)), 'value': 'enabled'}], ('enabled',) if workspace.attachments_enabled else ())},
        {'type': 'input', 'block_id': SIZE_INPUT, 'label': _plain(threadvault.localisation.translate('settings.size', language)), 'hint': _plain(threadvault.localisation.translate('settings.size.hint', language, maximum = str(threadvault.customisation.ATTACHMENT_SIZE_MAXIMUM))), 'element': {'type': 'number_input', 'action_id': SIZE_INPUT, 'is_decimal_allowed': False, 'min_value': '1', 'max_value': str(threadvault.customisation.ATTACHMENT_SIZE_MAXIMUM), 'initial_value': str(workspace.attachment_size_maximum)}},
        {'type': 'input', 'block_id': LANGUAGE_INPUT, 'label': _plain(threadvault.localisation.translate('settings.language', language)), 'hint': _plain(threadvault.localisation.translate('settings.language.hint', language)), 'element': {'type': 'radio_buttons', 'action_id': LANGUAGE_INPUT, 'options': list(languages.values()), 'initial_option': languages[workspace.markdown_language]}}
    ]

    return {'type': 'modal', 'callback_id': SETTINGS_CALLBACK, 'title': _plain(threadvault.localisation.translate('settings.title', language)), 'submit': _plain(threadvault.localisation.translate('settings.submit', language)), 'close': _plain(threadvault.localisation.translate('settings.close', language)), 'blocks': blocks}

def _button(
    *,
    github: GitHubState,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    if github == 'disconnected': return {'type': 'button', 'action_id': CONNECTION_ACTION, 'style': 'primary', 'text': _plain(threadvault.localisation.translate('home.github.connection', language))}
    if github == 'expired': return {'type': 'button', 'action_id': CONNECTION_ACTION, 'style': 'primary', 'text': _plain(threadvault.localisation.translate('home.github.reconnection', language))}

    return {'type': 'button', 'action_id': DISCONNECTION_ACTION, 'style': 'danger', 'text': _plain(threadvault.localisation.translate('home.github.disconnection', language)), 'confirm': _confirmation('disconnection', 'danger', language)}

def _confirmation(
    key: str,
    style: str,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    return {'title': _plain(threadvault.localisation.translate(f'{key}.title', language)), 'text': _plain(threadvault.localisation.translate(f'{key}.text', language)), 'confirm': _plain(threadvault.localisation.translate(f'{key}.confirm', language)), 'deny': _plain(threadvault.localisation.translate(f'{key}.deny', language)), 'style': style}

def _report(
    *,
    last: threadvault.journal.Run | None,
    role: threadvault.slack.permission.Role,
    language: threadvault.configuration.Language
) -> str:

    if last is None: return threadvault.localisation.translate('home.backup.missing', language)

    time = _date(last.completion)

    if last.commit is None: text, detail = threadvault.localisation.translate('home.backup.failure', language, time = time), last.reason
    else: text, detail = threadvault.localisation.translate('home.backup.success', language, time = time), f'<https://github.com/{last.repository}/commit/{last.commit}|{last.commit[:7]}>'

    return text if role == 'member' else f'{text}\n{detail}'

def _date(
    moment: datetime.datetime
) -> str:

    return f'<!date^{int(moment.timestamp())}^{{date_short}} {{time}}|{moment:%Y-%m-%d %H:%M} UTC>'

def _option(
    name: str
) -> dict[str, typing.Any]:

    return {'text': _plain(name if len(name) <= _DISPLAY_LIMIT else f'{name[:_DISPLAY_LIMIT - 1]}…'), 'value': name}

def _choice(
    user: str
) -> dict[str, typing.Any]:

    return {'text': {'type': 'mrkdwn', 'text': f'<@{user}>'}, 'value': user}

def _checkbox(
    action: str,
    options: list[dict[str, typing.Any]],
    values: tuple[str, ...]
) -> dict[str, typing.Any]:

    element = {'type': 'checkboxes', 'action_id': action, 'options': options}

    if (chosen := [option for option in options if option['value'] in values]): element['initial_options'] = chosen

    return element

def _text(
    title: str,
    text: str
) -> dict[str, str]:

    return {'type': 'mrkdwn', 'text': f'*{title}*\n{text}'}

def _plain(
    text: str
) -> dict[str, str]:

    return {'type': 'plain_text', 'text': text}

def _modal(
    title: str,
    text: str,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    return {'type': 'modal', 'title': _plain(title), 'close': _plain(threadvault.localisation.translate('modal.close', language)), 'blocks': [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}]}
