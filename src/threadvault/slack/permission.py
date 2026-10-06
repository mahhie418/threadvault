"""Roles of Slack users, which decide what each user sees and may do in the Slack app."""

import typing

import threadvault.configuration

type Role = typing.Literal['admin', 'member']

def role(
    settings: threadvault.configuration.Settings,
    user: str
) -> Role:

    """Tells the role of a Slack user.

    Args:
        settings: Settings of the deployment.
        user: Slack user ID.

    Returns:
        admin for the users in THREADVAULT_ADMIN_IDS, or member for anyone else.
    """

    return 'admin' if user in settings.threadvault_admin_ids else 'member'
