"""Views of the Slack app: the App Home and its modals."""

import typing

import threadvault.configuration
import threadvault.localisation
import threadvault.slack.permission

def home(
    *,
    connected: bool,
    destination: str | None,
    role: threadvault.slack.permission.Role,
    language: threadvault.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows the state of the backup.

    The owner and the admins also see the destination and their own role.

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

    return {'type': 'home', 'blocks': blocks}
