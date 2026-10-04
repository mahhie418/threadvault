import dataclasses
import datetime
import json
import os
import pathlib
import typing

import slack_sdk

import threadvault.backup.runner
import threadvault.customisation
import threadvault.vault.state

NOW = datetime.datetime(2026, 10, 5, 1, 0, tzinfo = datetime.UTC)

SETTINGS = threadvault.customisation.Settings(workspace_timezone = 'Asia/Tokyo', markdown_language = 'ja')

MESSAGES_DELETION = {'1510880400.000000', '1791075600.000001'}

THREAD_INSERTION = [
    {'latest_reply': '1791160200.000000', 'reply_count': 1, 'text': 'xxx', 'thread_ts': '1791158400.000000', 'ts': '1791158400.000000', 'type': 'message', 'user': 'UXXX1'},
    {'parent_user_id': 'UXXX1', 'text': 'xxx', 'thread_ts': '1791158400.000000', 'ts': '1791160200.000000', 'type': 'message', 'user': 'UXXX2'}
]

FILES_EXPECTED = [
    '.threadvault/state.json',
    'raw/channels.json',
    'raw/groups.json',
    'raw/users.json',
    'raw/xxx/2017-11-17.json',
    'raw/xxx/2026-10-04.json',
    'transcripts/index.md',
    'transcripts/xxx/2017-11.md',
    'transcripts/xxx/2026-10.md'
]

def locate(
    *names: str
) -> pathlib.Path:

    return pathlib.Path(os.path.join(pathlib.Path(__file__).parents[1], 'fixtures', *names))

def run(
    slack: slack_sdk.web.WebClient,
    vault: pathlib.Path,
    settings: threadvault.customisation.Settings = SETTINGS,
    limit: int | None = None
) -> list[threadvault.backup.runner.Result]:

    return threadvault.backup.runner.run(slack, vault, settings, days = 30, limit = limit, now = NOW)

def survey(
    root: pathlib.Path
) -> list[str]:

    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())

def read(
    vault: pathlib.Path,
    *names: str
) -> list[dict[str, typing.Any]]:

    return json.loads(pathlib.Path(os.path.join(vault, 'raw', *names)).read_text(encoding = 'utf-8'))

def test_runner_vault_creation(
    tmp_path: pathlib.Path,
    slack: slack_sdk.web.WebClient
) -> None:

    results = run(slack, tmp_path)
    expected = survey(locate('vault'))

    assert survey(tmp_path) == sorted([*expected, '.threadvault/state.json'])
    for name in expected: assert pathlib.Path(os.path.join(tmp_path, name)).read_bytes() == pathlib.Path(os.path.join(locate('vault'), name)).read_bytes()
    assert threadvault.vault.state.load(tmp_path) == {'CXXX1': 'general', 'CXXX2': 'xxx'}
    assert [result.messages for result in results] == [0, 5]

def test_runner_vault_update(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    run(slack, tmp_path)

    messages: list[dict[str, typing.Any]] = workspace['messages']['CXXX1']
    next(message for message in messages if message['ts'] == '1791075600.000000')['text'] = 'xxx2'
    workspace['messages']['CXXX1'] = [message for message in messages if message['ts'] not in MESSAGES_DELETION] + THREAD_INSERTION

    results = run(slack, tmp_path)
    transcript = pathlib.Path(os.path.join(tmp_path, 'transcripts', 'general', '2026-10.md')).read_text(encoding = 'utf-8')

    assert [message['ts'] for message in read(tmp_path, 'general', '2017-11-17.json')] == ['1510880400.000000', '1510963199.000000']
    assert [(message['ts'], message['text']) for message in read(tmp_path, 'general', '2026-10-04.json')] == [('1791072000.000000', 'xxx'), ('1791075600.000000', 'xxx2')]
    assert [message['ts'] for message in read(tmp_path, 'general', '2026-10-05.json')] == ['1791158400.000000', '1791160200.000000']
    assert results[1] == threadvault.backup.runner.Result(channel = 'CXXX1', directory = 'general', messages = 6, deleted = 1, withheld = 0)
    assert 'xxx2' in transcript
    assert 'p1791075600000001' not in transcript

def test_runner_vault_deletion(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    workspace['messages']['CXXX2'] = [{'text': 'xxx', 'ts': '1791075600.000000', 'type': 'message', 'user': 'UXXX1'}]

    run(slack, tmp_path)

    workspace['messages'] = {'CXXX1': [message for message in workspace['messages']['CXXX1'] if message['ts'] not in MESSAGES_DELETION], 'CXXX2': []}

    results = run(slack, tmp_path, limit = 1)

    assert [(result.deleted, result.withheld) for result in results] == [(1, 0), (0, 1)]
    assert [message['ts'] for message in read(tmp_path, 'general', '2026-10-04.json')] == ['1791072000.000000', '1791075600.000000', '1791075600.000001']

def test_runner_vault_state(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    run(slack, tmp_path)

    pathlib.Path(os.path.join(tmp_path, '.threadvault', 'state.json')).unlink()
    workspace['messages']['CXXX1'] = [message for message in workspace['messages']['CXXX1'] if message['ts'] not in MESSAGES_DELETION]

    results = run(slack, tmp_path)

    assert results[1] == threadvault.backup.runner.Result(channel = 'CXXX1', directory = 'general', messages = 5, deleted = 0, withheld = 1)

def test_runner_vault_rename(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    run(slack, tmp_path)

    for channel in workspace['channels']: channel['name'] = {'CXXX1': 'xxx', 'CXXX2': 'general'}[channel['id']]

    run(slack, tmp_path)

    assert survey(tmp_path) == FILES_EXPECTED
    assert threadvault.vault.state.load(tmp_path) == {'CXXX1': 'xxx', 'CXXX2': 'general'}

def test_runner_vault_addition(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    channel = next(channel for channel in workspace['channels'] if channel['id'] == 'CXXX1')
    channel['is_member'] = False

    assert [result.channel for result in run(slack, tmp_path)] == ['CXXX2']

    channel['is_member'] = True

    results = run(slack, tmp_path)

    assert results[1] == threadvault.backup.runner.Result(channel = 'CXXX1', directory = 'general', messages = 5, deleted = 0, withheld = 0)

def test_runner_vault_selection(
    tmp_path: pathlib.Path,
    slack: slack_sdk.web.WebClient
) -> None:

    results = run(slack, tmp_path, dataclasses.replace(SETTINGS, channel_mode = 'selected', channels_selected = ('CXXX2',)))

    assert [result.channel for result in results] == ['CXXX2']
    assert [channel['id'] for channel in read(tmp_path, 'groups.json')] == ['CXXX2']
    assert read(tmp_path, 'channels.json') == []
    assert threadvault.vault.state.load(tmp_path) == {'CXXX2': 'xxx'}
