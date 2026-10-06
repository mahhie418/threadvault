"""Roles of Slack users, which decide what each user sees and may do in the Slack app."""

import typing

import threadvault.configuration

type Role = typing.Literal['owner', 'admin', 'member']

def role(
    settings: threadvault.configuration.Settings,
    user: str
) -> Role:

    """Tells the role of a Slack user.

    Args:
        settings: Settings of the deployment.
        user: Slack user ID.

    Returns:
        owner for the user in THREADVAULT_OWNER_ID, who installed the app,
        admin for the users in THREADVAULT_ADMIN_IDS, or member for anyone else.
    """

    if user == settings.threadvault_owner_id: return 'owner'

    return 'admin' if user in settings.threadvault_admin_ids else 'member'
