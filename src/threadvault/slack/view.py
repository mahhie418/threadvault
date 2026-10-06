"""Views of the Slack app: the App Home and its modals."""

import typing

import threadvault.configuration
import threadvault.github.oauth
import threadvault.localisation
import threadvault.slack.permission

CONNECTION_ACTION = 'connection_action'

def home(
    *,
    connected: bool,
    destination: str | None,
    role: threadvault.slack.permission.Role,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows the state of the backup.

    The owner and the admins also see the destination and their own role,
    and a button that connects GitHub while it is not connected.

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

    if role != 'member' and not connected: blocks.append({'type': 'actions', 'elements': [{'type': 'button', 'action_id': CONNECTION_ACTION, 'style': 'primary', 'text': _plain(threadvault.localisation.translate('home.github.connection', language))}]})

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
