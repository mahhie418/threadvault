"""Roles of Slack users, which decide what each user sees and may do in the Slack app."""

import collections.abc
import typing

import slack_bolt

import threadvault.configuration
import threadvault.customisation

type Role = typing.Literal['owner', 'operator', 'admin', 'member']

def owner(
    settings: threadvault.configuration.Settings,
    workspace: threadvault.customisation.Settings
) -> str:

    """Tells who owns the app.

    Args:
        settings: Settings of the deployment.
        workspace: Settings of the workspace, with the owner since a transfer.

    Returns:
        Slack user ID of the owner: the admin to whom the ownership was last
        transferred, or the user in THREADVAULT_OWNER_ID before any transfer.
    """

    return workspace.owner_id or settings.threadvault_owner_id

def admins(
    settings: threadvault.configuration.Settings,
    workspace: threadvault.customisation.Settings
) -> frozenset[str]:

    """Tells who the admins are, the owner among them.

    Args:
        settings: Settings of the deployment.
        workspace: Settings of the workspace, with the owner since a transfer.

    Returns:
        Slack user IDs of the users in THREADVAULT_ADMIN_IDS, of the user in
        THREADVAULT_OWNER_ID, who stays an admin after a transfer, and of the
        owner.
    """

    return settings.threadvault_admin_ids | {settings.threadvault_owner_id, owner(settings, workspace)}

def role(
    settings: threadvault.configuration.Settings,
    workspace: threadvault.customisation.Settings,
    user: str
) -> Role:

    """Tells the role of a Slack user.

    Args:
        settings: Settings of the deployment.
        workspace: Settings of the workspace, with the owner since a transfer and the admins allowed to operate the app.
        user: Slack user ID.

    Returns:
        owner for the owner, operator for the admins whom the owner allows to
        operate the app, admin for the other admins, or member for anyone else.
    """

    if user == owner(settings, workspace): return 'owner'
    if user not in admins(settings, workspace): return 'member'

    return 'operator' if user in workspace.admins_allowed else 'admin'

def restrict(
    settings: threadvault.configuration.Settings,
    store: threadvault.customisation.SettingsIO,
    roles: frozenset[Role]
) -> collections.abc.Callable[..., slack_bolt.BoltResponse | None]:

    """Builds a middleware that lets only some roles act in the app.

    Events, such as an opened App Home, reach the listeners whoever caused
    them. Any other request, such as a pressed button, reaches them only
    from a user with one of the roles; from anyone else, it is acknowledged
    and dropped, so that no listener acts for them even if a view showed
    them a button.

    Args:
        settings: Settings of the deployment.
        store: Settings of each workspace.
        roles: Roles that may act.

    Returns:
        The middleware, for `slack_bolt.App.use` or the middleware of a listener.
    """

    def check(
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext,
        ack: slack_bolt.Ack,
        next_: collections.abc.Callable[[], None]
    ) -> slack_bolt.BoltResponse | None:

        if body.get('type') != 'event_callback' and (context.team_id is None or context.user_id is None or role(settings, store.load(context.team_id), context.user_id) not in roles): return ack()

        return next_()

    return check
