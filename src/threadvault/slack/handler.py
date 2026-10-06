"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import typing

import slack_bolt

import threadvault.configuration
import threadvault.customisation
import threadvault.github.token
import threadvault.localisation
import threadvault.slack.permission
import threadvault.slack.view
import threadvault.storage

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
    language of the Slack locale of its viewer.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the settings of each workspace.
        manager: GitHub tokens of the deployment.
    """

    store = threadvault.customisation.SettingsIO(database)

    def publish(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if event.get('tab') != 'home' or context.team_id is None: return

        workspace = store.load(context.team_id)
        user = application.client.users_info(user = event['user'], include_locale = True).get('user', {})
        language = threadvault.localisation.choose(user.get('locale'), settings.threadvault_language_display)
        application.client.views_publish(user_id = event['user'], view = threadvault.slack.view.home(connected = manager.connected(), destination = workspace.repository_name, role = threadvault.slack.permission.role(settings, event['user']), language = language))

    application.event('app_home_opened')(publish)
