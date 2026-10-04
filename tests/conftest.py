import decimal
import json
import os
import pathlib
import typing

import pytest
import slack_sdk

class Slack(slack_sdk.web.WebClient):

    def __init__(
        self,
        workspace: dict[str, typing.Any]
    ) -> None:

        super().__init__()

        self.workspace = workspace

    @typing.override
    def api_call(
        self,
        api_method: str,
        *,
        http_verb: str = 'POST',
        params: dict[str, typing.Any] | None = None,
        **_: object
    ) -> slack_sdk.web.SlackResponse:

        arguments = {key: value for key, value in (params or {}).items() if value is not None}
        types: str = arguments.get('types', 'public_channel')
        conversations: dict[str, list[dict[str, typing.Any]]] = self.workspace['messages']
        messages: list[dict[str, typing.Any]] = sorted(conversations.get(arguments.get('channel', ''), []), key = lambda message: decimal.Decimal(message['ts']))

        match api_method:

            case 'users.list': key, entries = 'members', self.workspace['users']
            case 'conversations.list': key, entries = 'channels', [channel for channel in self.workspace['channels'] if ('private_channel' if channel['is_private'] else 'public_channel') in types.split(',')]
            case 'conversations.members': key, entries = 'members', self.workspace['members'][arguments['channel']]
            case 'conversations.history': key, entries = 'messages', [message for message in reversed(messages) if message.get('thread_ts', message['ts']) == message['ts'] and within(message, arguments)]
            case 'conversations.replies': key, entries = 'messages', [message for message in messages if message.get('thread_ts') == arguments['ts']]
            case _: raise NotImplementedError(api_method)

        offset = int(arguments.get('cursor', 0))
        cursor = str(offset + 1) if offset + 1 < len(entries) else ''
        body = {'ok': True, key: entries[offset:offset + 1], 'response_metadata': {'next_cursor': cursor}}

        return slack_sdk.web.SlackResponse(client = self, http_verb = http_verb, api_url = api_method, req_args = {'params': arguments}, data = body, headers = {}, status_code = 200)

@pytest.fixture
def workspace() -> dict[str, typing.Any]:

    directory = pathlib.Path(os.path.join(pathlib.Path(__file__).parent, 'fixtures', 'slack'))
    users, channels, members, messages = (json.loads(pathlib.Path(os.path.join(directory, name)).read_text(encoding = 'utf-8')) for name in ('users.list.json', 'conversations.list.json', 'conversations.members.json', 'messages.json'))

    return {'users': users, 'channels': channels, 'members': members, 'messages': {'CXXX1': messages}}

@pytest.fixture
def slack(
    workspace: dict[str, typing.Any]
) -> Slack:

    return Slack(workspace)

def within(
    message: dict[str, typing.Any],
    arguments: dict[str, typing.Any]
) -> bool:

    ts, oldest, latest = (decimal.Decimal(value) for value in (message['ts'], arguments['oldest'], arguments['latest']))

    return oldest < ts < latest or (arguments.get('inclusive', False) and ts in {oldest, latest})
