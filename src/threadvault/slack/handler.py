"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import collections.abc
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
    act in the app, as `threadvault.slack.permission.restrict` makes sure.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the settings of each workspace.
        manager: GitHub tokens of the deployment.
    """

    store = threadvault.customisation.SettingsIO(database)

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

        application.client.views_publish(user_id = user, view = threadvault.slack.view.home(connected = manager.connected(), destination = workspace.repository_name, role = threadvault.slack.permission.role(settings, user), language = choose(user)))

    def show(
        modal: str,
        view: dict[str, typing.Any]
    ) -> None:

        try: application.client.views_update(view_id = modal, view = view)
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Modal not updated, perhaps because it was closed: %s', error)

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

    application.use(threadvault.slack.permission.restrict(settings))
    application.event('app_home_opened')(publish)
    application.action(threadvault.slack.view.CONNECTION_ACTION)(connect)

def detach(
    function: collections.abc.Callable[[], None]
) -> None:

    """Runs a function in a daemon thread, so that a listener returns at once and the app stops without waiting for it.

    Args:
        function: The function.
    """

    threading.Thread(target = function, daemon = True).start()
