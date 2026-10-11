import os
import pathlib
import typing

import httpx
import pytest
import respx
import slack_sdk
import slack_sdk.errors
import slack_sdk.http_retry

import threadvault.slack.api

HANDLERS = (slack_sdk.http_retry.builtin_handlers.RateLimitErrorRetryHandler, slack_sdk.http_retry.builtin_handlers.ServerErrorRetryHandler, slack_sdk.http_retry.builtin_handlers.ConnectionErrorRetryHandler)

FILE_VALID = {'id': 'FXXX', 'mimetype': 'text/plain', 'url_private_download': 'https://files.slack.com/xxx'}

MIMETYPES_ACCEPTED = [('text/plain', 'text/plain'), ('text/html', 'text/html; charset=utf-8')]

DOWNLOADS_FAILED = [
    (httpx.Response(404), 'answered 404'),
    (httpx.Response(200, content = b'xxx', headers = {'content-type': 'text/html; charset=utf-8'}), 'web page'),
    (httpx.Response(200, content = b'xxxx', headers = {'content-type': 'text/plain'}), 'larger than 3 bytes'),
    (httpx.ConnectError('xxx'), 'could not be downloaded')
]

def test_api_client_retry() -> None:

    client = threadvault.slack.api.connect('xoxb-xxx')

    assert {type(handler): handler.max_retry_count for handler in client.retry_handlers} == dict.fromkeys(HANDLERS, threadvault.slack.api.RETRY_LIMIT)

def test_api_user_pagination(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    assert threadvault.slack.api.users(slack) == workspace['users']

def test_api_channel_exclusion(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    channels = list(workspace['channels'])
    workspace['channels'] += [channels[0] | {'id': 'CXXX3', 'is_ext_shared': True}, channels[0] | {'id': 'CXXX4', 'is_pending_ext_shared': True}]

    assert threadvault.slack.api.channels(slack) == channels

def test_api_channel_join(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    threadvault.slack.api.join(slack, 'CXXX1')

    assert workspace['calls'] == [('conversations.join', {'channel': 'CXXX1'})]

def test_api_member_pagination(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    assert threadvault.slack.api.members(slack, 'CXXX1') == workspace['members']['CXXX1']

def test_api_history_window(
    slack: slack_sdk.web.WebClient
) -> None:

    messages = threadvault.slack.api.history(slack, 'CXXX1', oldest = '1510880400.000000', latest = '1791075600.000000')

    assert [message['ts'] for message in messages] == ['1791075600.000000', '1510963199.000000', '1510880400.000000']

def test_api_thread_comprehensiveness(
    slack: slack_sdk.web.WebClient
) -> None:

    messages = threadvault.slack.api.replies(slack, 'CXXX1', '1510963199.000000')

    assert [message['ts'] for message in messages] == ['1510963199.000000', '1791072000.000000']

def test_api_thread_absence(
    slack: slack_sdk.web.WebClient
) -> None:

    assert threadvault.slack.api.replies(slack, 'CXXX1', '1791158400.000000') == []

def test_api_thread_failure(
    slack: slack_sdk.web.WebClient
) -> None:

    with pytest.raises(slack_sdk.errors.SlackApiError, match = 'channel_not_found'): threadvault.slack.api.replies(slack, 'CXXX9', '1510963199.000000')

@pytest.mark.parametrize(('mimetype', 'category'), MIMETYPES_ACCEPTED)
def test_api_file_download(
    tmp_path: pathlib.Path,
    mimetype: str,
    category: str
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, 'xxx', 'xxx.txt'))

    with respx.mock:

        route = respx.get(FILE_VALID['url_private_download']).respond(200, content = b'xxx', headers = {'content-type': category})
        threadvault.slack.api.download(threadvault.slack.api.connect('xoxb-xxx'), FILE_VALID | {'mimetype': mimetype}, path, limit = 3)

    assert [entry.name for entry in path.parent.iterdir()] == ['xxx.txt']
    assert path.read_bytes() == b'xxx'
    assert route.calls.last.request.headers['authorization'] == 'Bearer xoxb-xxx'

@pytest.mark.parametrize(('response', 'message'), DOWNLOADS_FAILED)
def test_api_file_failure(
    tmp_path: pathlib.Path,
    response: httpx.Response | Exception,
    message: str
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, 'xxx', 'xxx.txt'))

    with respx.mock:

        respx.get(FILE_VALID['url_private_download']).mock(side_effect = [response])

        with pytest.raises(threadvault.slack.api.DownloadError, match = message): threadvault.slack.api.download(threadvault.slack.api.connect('xoxb-xxx'), FILE_VALID, path, limit = 3)

    assert list(path.parent.iterdir()) == []
