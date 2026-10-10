"""Calls to Slack for the backup: the Web API, with pagination and retries, and file downloads."""

import collections.abc
import pathlib
import typing

import httpx
import slack_sdk
import slack_sdk.errors
import slack_sdk.http_retry

PAGE_SIZE = 200

TIMEOUT_LIMIT = 30.
RETRY_LIMIT = 5

class DownloadError(Exception):

    """Raised when an attached file cannot be downloaded from Slack."""

def connect(
    token: str
) -> slack_sdk.web.WebClient:

    """Creates a client that sends a request again after a rate limit, a server error or a lost connection.

    A request is sent up to `RETRY_LIMIT` more times. After a rate limit,
    the client first waits as long as Slack asks.

    Args:
        token: Slack bot token (xoxb-...).

    Returns:
        The client.
    """

    handlers: list[slack_sdk.http_retry.RetryHandler] = [
        slack_sdk.http_retry.builtin_handlers.RateLimitErrorRetryHandler(max_retry_count = RETRY_LIMIT),
        slack_sdk.http_retry.builtin_handlers.ServerErrorRetryHandler(max_retry_count = RETRY_LIMIT),
        slack_sdk.http_retry.builtin_handlers.ConnectionErrorRetryHandler(max_retry_count = RETRY_LIMIT)
    ]

    return slack_sdk.web.WebClient(token = token, retry_handlers = handlers)

def users(
    client: slack_sdk.web.WebClient
) -> list[dict[str, typing.Any]]:

    """Fetches every user of the workspace, deactivated users and bots included.

    Args:
        client: Slack client for the workspace.

    Returns:
        The users, as users.list returns them.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    return _paginate(client.users_list, 'members')

def channels(
    client: slack_sdk.web.WebClient
) -> list[dict[str, typing.Any]]:

    """Fetches the public and private channels that the bot can see, except Slack Connect channels.

    The bot sees every public channel, but a private channel only when it is
    a member. A channel that is shared with another organisation, or waiting
    to be, is left out.

    Args:
        client: Slack client for the workspace.

    Returns:
        The channels, as conversations.list returns them.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    entries: list[dict[str, typing.Any]] = _paginate(client.conversations_list, 'channels', types = 'public_channel,private_channel')

    return [channel for channel in entries if not (channel.get('is_ext_shared') or channel.get('is_pending_ext_shared'))]

def members(
    client: slack_sdk.web.WebClient,
    channel: str
) -> list[str]:

    """Fetches the members of a channel.

    Args:
        client: Slack client for the workspace.
        channel: ID of the channel.

    Returns:
        User IDs of the members.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    return _paginate(client.conversations_members, 'members', channel = channel)

def history(
    client: slack_sdk.web.WebClient,
    channel: str,
    *,
    oldest: str,
    latest: str
) -> list[dict[str, typing.Any]]:

    """Fetches the messages posted to a channel from `oldest` to `latest`, both included.

    Thread replies are not among them, except those also sent to the channel.

    Args:
        client: Slack client for the workspace.
        channel: ID of the channel.
        oldest: Timestamp of the oldest message to fetch.
        latest: Timestamp of the latest message to fetch.

    Returns:
        The messages, as conversations.history returns them.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    return _paginate(client.conversations_history, 'messages', channel = channel, oldest = oldest, latest = latest, inclusive = True)

def replies(
    client: slack_sdk.web.WebClient,
    channel: str,
    thread_ts: str
) -> list[dict[str, typing.Any]]:

    """Fetches a thread: the parent message and every reply.

    A thread whose parent message no longer exists has no messages.

    Args:
        client: Slack client for the workspace.
        channel: ID of the channel.
        thread_ts: Timestamp of the parent message.

    Returns:
        The messages, as conversations.replies returns them.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    try:

        return _paginate(client.conversations_replies, 'messages', channel = channel, ts = thread_ts)

    except slack_sdk.errors.SlackApiError as error:

        response: slack_sdk.web.SlackResponse = error.response

        if response.get('error') == 'thread_not_found': return []

        raise

def download(
    client: slack_sdk.web.WebClient,
    file: collections.abc.Mapping[str, typing.Any],
    path: pathlib.Path,
    *,
    limit: int
) -> None:

    """Downloads an attached file, bit by bit.

    The file is written next to `path` and moves there only when it is
    complete, so that a failure leaves nothing behind. A web page in place of
    a file that is not one means that Slack refused the token.

    Args:
        client: Slack client for the workspace, whose token the download uses.
        file: The file as Slack describes it in a message.
        path: Where to save the file. Missing parent directories are created.
        limit: Largest size of the file to accept, in bytes.

    Raises:
        DownloadError: Slack answered with an error or a web page, the file is
                       larger than `limit`, or the connection failed.
    """

    path.parent.mkdir(parents = True, exist_ok = True)
    temporary = path.with_name(f'{path.name}.tmp')

    try:

        with httpx.stream('GET', file['url_private_download'], headers = {'Authorization': f'Bearer {client.token}'}, follow_redirects = True, timeout = TIMEOUT_LIMIT) as response:

            received: str = response.headers.get('content-type', '')
            expected: str = file.get('mimetype', '')

            if response.is_error: raise DownloadError(f'Slack answered {response.status_code} for file {file['id']}')
            if received.startswith('text/html') and not expected.startswith('text/html'): raise DownloadError(f'Slack sent a web page instead of file {file['id']}')

            with temporary.open('wb') as stream:

                for chunk in response.iter_bytes():

                    if stream.tell() + len(chunk) > limit: raise DownloadError(f'File {file['id']} is larger than {limit} bytes')

                    stream.write(chunk)

    except BaseException as error:

        temporary.unlink(missing_ok = True)

        if isinstance(error, httpx.HTTPError): raise DownloadError(f'File {file['id']} could not be downloaded: {error}') from error

        raise

    temporary.replace(path)

def _paginate(
    method: collections.abc.Callable[..., slack_sdk.web.SlackResponse],
    key: str,
    **arguments: str | bool
) -> list[typing.Any]:

    entries: list[typing.Any] = []
    cursor = None

    while True:

        response = method(cursor = cursor, limit = PAGE_SIZE, **arguments)
        page: list[typing.Any] = response.get(key, [])
        metadata: dict[str, str] = response.get('response_metadata', {})

        entries.extend(page)

        if not (cursor := metadata.get('next_cursor')): return entries
