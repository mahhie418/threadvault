"""Views of the Slack app: the App Home and its modals."""

import json
import typing

import threadvault.configuration
import threadvault.github.oauth
import threadvault.localisation
import threadvault.slack.permission

CONNECTION_ACTION = 'connection_action'
PERMISSIONS_ACTION = 'permissions_action'
PERMISSIONS_CALLBACK = 'permissions_callback'
PERMISSIONS_CONFIRMATION = 'permissions_confirmation'

ADMINS_INPUT = 'admins_input'

_CHECKBOX_LIMIT = 10

def home(
    *,
    connected: bool,
    destination: str | None,
    role: threadvault.slack.permission.Role,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows the state of the backup.

    The owner and the admins also see the destination and their own role.
    The owner and the admins allowed to operate the app see a button that
    connects GitHub while it is not connected, and the owner also sees a
    button that chooses the admins allowed to operate the app.

    Args:
        connected: Whether GitHub is connected.
        destination: Repository of the vault, as owner/name, or None while none is chosen.
        role: Role of the viewer.
        language: Language of the viewer.

    Returns:
        The view, as views.publish takes it.
    """

    fields = [(threadvault.localisation.translate('home.github', language), threadvault.localisation.translate('home.github.connected' if connected else 'home.github.disconnected', language))]
    blocks = []

    if role != 'member':

        fields.append((threadvault.localisation.translate('home.destination', language), f'<https://github.com/{destination}|{destination}>' if destination else threadvault.localisation.translate('home.destination.missing', language)))
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': threadvault.localisation.translate(f'home.role.{role}', language)}]})

    blocks.append({'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'*{title}*\n{text}'} for title, text in fields]})

    if role in ('owner', 'operator') and not connected: blocks.append({'type': 'actions', 'elements': [{'type': 'button', 'action_id': CONNECTION_ACTION, 'style': 'primary', 'text': _plain(threadvault.localisation.translate('home.github.connection', language))}]})
    if role == 'owner': blocks.append({'type': 'actions', 'elements': [{'type': 'button', 'action_id': PERMISSIONS_ACTION, 'text': _plain(threadvault.localisation.translate('home.permissions', language))}]})

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
        element: dict[str, typing.Any] = {'type': 'checkboxes', 'action_id': ADMINS_INPUT, 'options': [_choice(admin) for admin in group]}

        if (chosen := [_choice(admin) for admin in group if admin in allowed]): element['initial_options'] = chosen

        blocks.append({'type': 'input', 'block_id': f'{ADMINS_INPUT}{index // _CHECKBOX_LIMIT}', 'optional': True, 'label': _plain(threadvault.localisation.translate('permissions.label', language)), 'element': element})

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

def _choice(
    user: str
) -> dict[str, typing.Any]:

    return {'text': {'type': 'mrkdwn', 'text': f'<@{user}>'}, 'value': user}

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
