"""Roles of Slack users, which decide what each user sees and may do in the Slack app."""

import collections.abc
import typing

import slack_bolt

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

def restrict(
    settings: threadvault.configuration.Settings
) -> collections.abc.Callable[..., slack_bolt.BoltResponse | None]:

    """Builds a middleware that lets only the owner and the admins act in the app.

    Events, such as an opened App Home, reach the listeners whoever caused
    them. Any other request, such as a pressed button, reaches them only
    from the owner or an admin; from anyone else, it is acknowledged and
    dropped, so that no listener acts for them even if a view showed them a
    button.

    Args:
        settings: Settings of the deployment.

    Returns:
        The middleware, for `slack_bolt.App.use`.
    """

    def check(
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext,
        ack: slack_bolt.Ack,
        next_: collections.abc.Callable[[], None]
    ) -> slack_bolt.BoltResponse | None:

        if body.get('type') != 'event_callback' and (context.user_id is None or role(settings, context.user_id) == 'member'): return ack()

        return next_()

    return check
