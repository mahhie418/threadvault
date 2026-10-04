import typing

import slack_sdk
import slack_sdk.http_retry

import threadvault.slack.api

HANDLERS = (slack_sdk.http_retry.builtin_handlers.RateLimitErrorRetryHandler, slack_sdk.http_retry.builtin_handlers.ServerErrorRetryHandler, slack_sdk.http_retry.builtin_handlers.ConnectionErrorRetryHandler)

def test_api_client_retry() -> None:

    client = threadvault.slack.api.connect('xoxb-xxx')

    assert {type(handler): handler.max_retry_count for handler in client.retry_handlers} == dict.fromkeys(HANDLERS, threadvault.slack.api.RETRY_LIMIT)

def test_api_users_pagination(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    assert threadvault.slack.api.users(slack) == workspace['users']

def test_api_channels_exclusion(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    channels = list(workspace['channels'])
    workspace['channels'] += [channels[0] | {'id': 'CXXX3', 'is_ext_shared': True}, channels[0] | {'id': 'CXXX4', 'is_pending_ext_shared': True}]

    assert threadvault.slack.api.channels(slack) == channels

def test_api_members_pagination(
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
