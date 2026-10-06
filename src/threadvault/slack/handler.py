"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import collections.abc
import dataclasses
import json
import logging
import threading
import typing

import slack_bolt
import slack_sdk.errors

import threadvault.configuration
import threadvault.customisation
import threadvault.github.oauth
import threadvault.github.token
import threadvault.localisation
import threadvault.product
import threadvault.slack.permission
import threadvault.slack.view
import threadvault.storage

_LOGGER = logging.getLogger(__name__)

def register(
    application: slack_bolt.App,
    settings: threadvault.configuration.Settings,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    """Registers the listeners of the app.

    The listeners call Slack with the client of the app, which holds the bot
    token of the one workspace, rather than with a client per request. What
    a view shows depends on the role of its viewer, and each view is in the
    language of the Slack locale of its viewer. Only the owner and the admins
    allowed to operate the app act in it, and only the owner changes the
    permissions of the admins, as `threadvault.slack.permission.restrict`
    makes sure. When the permissions change, both the admin and the owner
    hear of it by direct message.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the settings of each workspace.
        manager: GitHub tokens of the deployment.
    """

    store = threadvault.customisation.SettingsIO(database)
    guard = [threadvault.slack.permission.restrict(settings, store, frozenset({'owner'}))]

    def choose(
        user: str
    ) -> threadvault.configuration.Language:

        entry: dict[str, typing.Any] = application.client.users_info(user = user, include_locale = True).get('user', {})

        return threadvault.localisation.choose(entry.get('locale'), settings.threadvault_language_display)

    def refresh(
        team: str,
        user: str
    ) -> None:

        workspace = store.load(team)

        application.client.views_publish(user_id = user, view = threadvault.slack.view.home(connected = manager.connected(), destination = workspace.repository_name, role = threadvault.slack.permission.role(settings, workspace, user), language = choose(user)))

    def show(
        modal: str,
        view: dict[str, typing.Any]
    ) -> None:

        try: application.client.views_update(view_id = modal, view = view)
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Modal not updated, perhaps because it was closed: %s', error)

    def tell(
        recipient: str,
        key: str,
        **values: str
    ) -> None:

        try: application.client.chat_postMessage(channel = recipient, text = threadvault.localisation.translate(key, choose(recipient), **values))
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Direct message to %s not sent: %s', recipient, error)

    def link(
        team: str,
        user: str,
        modal: str,
        language: threadvault.configuration.Language
    ) -> None:

        try:

            code = threadvault.github.oauth.request(settings.github_app_client_id)
            show(modal, threadvault.slack.view.connect(code = code, language = language))
            manager.save(threadvault.github.oauth.poll(settings.github_app_client_id, code))

        except threadvault.github.oauth.OAuthError as error:

            show(modal, threadvault.slack.view.respond(error = error, language = language))

            return

        refresh(team, user)
        show(modal, threadvault.slack.view.respond(error = None, language = language))

    def publish(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if event.get('tab') != 'home' or context.team_id is None: return

        refresh(context.team_id, event['user'])

    def connect(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        language = choose(user)
        opening: dict[str, typing.Any] = application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.connect(code = None, language = language)).get('view', {})

        detach(lambda: link(team, user, opening['id'], language))

    def manage(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        admins = sorted(settings.threadvault_admin_ids - {settings.threadvault_owner_id})

        application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.permit(admins = admins, allowed = store.load(context.team_id).admins_allowed, language = choose(context.user_id)))

    def review(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if context.team_id is None or context.user_id is None: return

        admins = settings.threadvault_admin_ids - {settings.threadvault_owner_id}
        allowed = set(store.load(context.team_id).admins_allowed) & admins
        values: dict[str, dict[str, dict[str, typing.Any]]] = view['state']['values']
        chosen = {option['value'] for block in values.values() for element in block.values() for option in element['selected_options']}
        granted, revoked = sorted(chosen - allowed), sorted(allowed - chosen)
        language = choose(context.user_id)

        if granted or revoked: ack(response_action = 'push', view = threadvault.slack.view.review(granted = granted, revoked = revoked, language = language))
        else: ack(response_action = 'errors', errors = {f'{threadvault.slack.view.ADMINS_INPUT}0': threadvault.localisation.translate('permissions.unchanged', language)})

    def apply(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, owner = context.team_id, context.user_id

        if team is None or owner is None: return

        changes: dict[str, list[str]] = json.loads(view['private_metadata'])
        workspace = store.load(team)
        allowed = (set(workspace.admins_allowed) | set(changes['granted'])) - set(changes['revoked'])

        store.save(team, dataclasses.replace(workspace, admins_allowed = tuple(sorted(allowed))), update_user = owner)
        ack(response_action = 'clear')

        for user in [owner, *changes['granted'], *changes['revoked']]: refresh(team, user)

        for user in changes['granted']:

            tell(user, 'notice.grant', owner = owner, product = threadvault.product.NAME)
            tell(owner, 'notice.grant.done', user = user, product = threadvault.product.NAME)

        for user in changes['revoked']:

            tell(user, 'notice.revocation', owner = owner, product = threadvault.product.NAME)
            tell(owner, 'notice.revocation.done', user = user, product = threadvault.product.NAME)

    application.use(threadvault.slack.permission.restrict(settings, store, frozenset({'owner', 'operator'})))
    application.event('app_home_opened')(publish)
    application.action(threadvault.slack.view.CONNECTION_ACTION)(connect)
    application.action(threadvault.slack.view.PERMISSIONS_ACTION, middleware = guard)(manage)
    application.view(threadvault.slack.view.PERMISSIONS_CALLBACK, middleware = guard)(review)
    application.view(threadvault.slack.view.PERMISSIONS_CONFIRMATION, middleware = guard)(apply)

def detach(
    function: collections.abc.Callable[[], None]
) -> None:

    """Runs a function in a daemon thread, so that a listener returns at once and the app stops without waiting for it.

    Args:
        function: The function.
    """

    threading.Thread(target = function, daemon = True).start()
