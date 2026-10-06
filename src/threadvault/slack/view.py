"""Views of the Slack app: the App Home and its modals."""

import typing

import threadvault.slack.permission

def home(
    *,
    connected: bool,
    destination: str | None,
    role: threadvault.slack.permission.Role
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows the state of the backup.

    The destination is shown only to admins.

    Args:
        connected: Whether GitHub is connected.
        destination: Repository of the vault, as owner/name, or None while none is chosen.
        role: Role of the viewer.

    Returns:
        The view, as views.publish takes it.
    """

    fields = [('GitHub', 'Connected' if connected else 'Not connected')]

    if role != 'member': fields.append(('Destination', f'<https://github.com/{destination}|{destination}>' if destination else 'Not chosen'))

    return {'type': 'home', 'blocks': [{'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'*{title}*\n{text}'} for title, text in fields]}]}
