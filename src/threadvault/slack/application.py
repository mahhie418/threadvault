"""Slack app of the admins, connected to Slack through Socket Mode."""

import slack_bolt
import slack_bolt.adapter.socket_mode
import slack_sdk

def build(
    client: slack_sdk.web.WebClient
) -> slack_bolt.App:

    """Builds the Slack app.

    Args:
        client: Slack client with the bot token.

    Returns:
        The app.

    Raises:
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    return slack_bolt.App(token = client.token, client = client)

def start(
    application: slack_bolt.App,
    token: str
) -> None:

    """Connects the app to Slack through Socket Mode and serves it until the process stops.

    Args:
        application: The application.
        token: App-level token of the Slack app (xapp-...).
    """

    slack_bolt.adapter.socket_mode.SocketModeHandler(application, token).start()
