import collections.abc
import decimal
import json
import os
import pathlib
import shutil
import subprocess
import typing

import pytest
import slack_sdk

class Slack(slack_sdk.web.WebClient):

    def __init__(
        self,
        workspace: dict[str, typing.Any]
    ) -> None:

        super().__init__(token = 'xoxb-xxx')

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

            case 'auth.test': data = {'url': self.workspace['url']}
            case 'users.list': data = page('members', self.workspace['users'], arguments)
            case 'conversations.list': data = page('channels', [channel for channel in self.workspace['channels'] if ('private_channel' if channel['is_private'] else 'public_channel') in types.split(',')], arguments)
            case 'conversations.members': data = page('members', self.workspace['members'][arguments['channel']], arguments)
            case 'conversations.history': data = page('messages', [message for message in reversed(messages) if message.get('thread_ts', message['ts']) == message['ts'] and within(message, arguments)], arguments)
            case 'conversations.replies': data = page('messages', [message for message in messages if message.get('thread_ts') == arguments['ts']], arguments)
            case _: raise NotImplementedError(api_method)

        return slack_sdk.web.SlackResponse(client = self, http_verb = http_verb, api_url = api_method, req_args = {'params': arguments}, data = {'ok': True, **data}, headers = {}, status_code = 200)

@pytest.fixture
def workspace() -> dict[str, typing.Any]:

    directory = pathlib.Path(os.path.join(pathlib.Path(__file__).parent, 'fixtures', 'slack'))
    users, channels, members, messages = (json.loads(pathlib.Path(os.path.join(directory, name)).read_text(encoding = 'utf-8')) for name in ('users.list.json', 'conversations.list.json', 'conversations.members.json', 'messages.json'))

    return {'url': 'https://xxx.slack.com/', 'users': users, 'channels': channels, 'members': members, 'messages': {'CXXX1': messages}}

@pytest.fixture
def slack(
    workspace: dict[str, typing.Any]
) -> Slack:

    return Slack(workspace)

@pytest.fixture
def git() -> collections.abc.Callable[..., str]:

    return execute

@pytest.fixture
def remote(
    tmp_path: pathlib.Path
) -> pathlib.Path:

    path = pathlib.Path(os.path.join(tmp_path, 'remote.git'))
    seed = pathlib.Path(os.path.join(tmp_path, 'seed'))

    execute('init', '--quiet', '--bare', '--initial-branch=main', str(path), directory = tmp_path)
    execute('clone', '--quiet', str(path), str(seed), directory = tmp_path)
    pathlib.Path(os.path.join(seed, 'README.md')).write_text('# xxx', encoding = 'utf-8')
    execute('add', '--all', directory = seed)
    execute('commit', '--quiet', '--message', 'xxx', directory = seed)
    execute('push', '--quiet', 'origin', 'HEAD:main', directory = seed)

    return path

def execute(
    *arguments: str,
    directory: pathlib.Path
) -> str:

    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')} | {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'xxx', 'GIT_AUTHOR_EMAIL': 'xxx@xxx.xxx', 'GIT_COMMITTER_NAME': 'xxx', 'GIT_COMMITTER_EMAIL': 'xxx@xxx.xxx'}

    return subprocess.run([str(shutil.which('git')), *arguments], cwd = directory, env = environment, capture_output = True, encoding = 'utf-8', check = True).stdout

def page(
    key: str,
    entries: list[typing.Any],
    arguments: dict[str, typing.Any]
) -> dict[str, typing.Any]:

    offset = int(arguments.get('cursor', 0))
    cursor = str(offset + 1) if offset + 1 < len(entries) else ''

    return {key: entries[offset:offset + 1], 'response_metadata': {'next_cursor': cursor}}

def within(
    message: dict[str, typing.Any],
    arguments: dict[str, typing.Any]
) -> bool:

    ts, oldest, latest = (decimal.Decimal(value) for value in (message['ts'], arguments['oldest'], arguments['latest']))

    return oldest < ts < latest or (arguments.get('inclusive', False) and ts in {oldest, latest})
