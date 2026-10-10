import collections.abc
import dataclasses
import datetime
import json
import os
import pathlib
import typing

import httpx
import pytest
import respx
import slack_sdk

import threadvault.backup.backlog
import threadvault.backup.runner
import threadvault.customisation
import threadvault.github.rest
import threadvault.slack.api
import threadvault.vault.repository
import threadvault.vault.state

NOW = datetime.datetime(2026, 10, 5, 1, 0, tzinfo = datetime.UTC)

SETTINGS = threadvault.customisation.Settings(workspace_timezone = 'Asia/Tokyo', markdown_language = 'ja')
REPOSITORY = f'{threadvault.github.rest.API_URL}/repos/xxx/xxx'

MESSAGES_DELETION = {'1510880400.000000', '1791075600.000001'}

THREAD_INSERTION = [
    {'latest_reply': '1791160200.000000', 'reply_count': 1, 'text': 'xxx', 'thread_ts': '1791158400.000000', 'ts': '1791158400.000000', 'type': 'message', 'user': 'UXXX1'},
    {'parent_user_id': 'UXXX1', 'text': 'xxx', 'thread_ts': '1791158400.000000', 'ts': '1791160200.000000', 'type': 'message', 'user': 'UXXX2'}
]

REPLY_THREAD = {'parent_user_id': 'UXXX1', 'text': 'xxx', 'thread_ts': '1510963199.000000', 'ts': '1791158400.000000', 'type': 'message', 'user': 'UXXX2'}

BACKLOG_THREAD = threadvault.backup.backlog.Backlog(threads = {'CXXX1': frozenset({'1510963199.000000', '1791158400.000001'})})

ATTACHMENT_CONTENT = [
    {'created': 1791158400, 'id': 'FXXX1', 'mimetype': 'text/plain', 'mode': 'hosted', 'name': 'xxx.txt', 'permalink': 'https://xxx.slack.com/files/UXXX1/FXXX1/xxx.txt', 'size': 3, 'url_private_download': 'https://files.slack.com/xxx1'},
    {'created': 1791158400, 'id': 'FXXX2', 'mimetype': 'text/plain', 'mode': 'hosted', 'name': 'xxx.txt', 'permalink': 'https://xxx.slack.com/files/UXXX1/FXXX2/xxx.txt', 'size': 3, 'url_private_download': 'https://files.slack.com/xxx2'},
    {'created': 1791158400, 'id': 'FXXX3', 'mimetype': 'text/plain', 'mode': 'hosted', 'name': 'xxx.txt', 'permalink': 'https://xxx.slack.com/files/UXXX1/FXXX3/xxx.txt', 'size': 1024 * 1024 * 21, 'url_private_download': 'https://files.slack.com/xxx3'}
]

ATTACHMENT_LINK = [
    '- [xxx.txt](../../attachments/2026-10/FXXX1/xxx.txt)',
    '- [xxx.txt](https://xxx.slack.com/files/UXXX1/FXXX2/xxx.txt)',
    '- [xxx.txt](https://xxx.slack.com/files/UXXX1/FXXX3/xxx.txt)'
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

FILES_PUBLISHED = [
    '.gitattributes',
    '.threadvault/state.json',
    'README.md',
    'raw/channels.json',
    'raw/general/2017-11-17.json',
    'raw/general/2026-10-04.json',
    'raw/groups.json',
    'raw/users.json',
    'transcripts/general/2017-11.md',
    'transcripts/general/2026-10.md',
    'transcripts/index.md'
]

def locate(
    *names: str
) -> pathlib.Path:

    return pathlib.Path(os.path.join(pathlib.Path(__file__).parents[1], 'fixtures', *names))

def run(
    slack: slack_sdk.web.WebClient,
    vault: pathlib.Path,
    settings: threadvault.customisation.Settings = SETTINGS,
    limit: int | None = None,
    backlog: threadvault.backup.backlog.Backlog | None = None
) -> list[threadvault.backup.runner.Result]:

    return threadvault.backup.runner.run(slack, vault, settings, days = 30, limit = limit, now = NOW, backlog = backlog)

def publish(
    slack: slack_sdk.web.WebClient,
    directory: pathlib.Path,
    backlog: threadvault.backup.backlog.Backlog | None = None
) -> tuple[list[threadvault.backup.runner.Result], str]:

    return threadvault.backup.runner.publish(slack, SETTINGS, directory = directory, full_name = 'xxx/xxx', token = lambda: 'ghu_xxx', days = 30, limit = None, now = NOW, backlog = backlog)

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
    assert results[1] == threadvault.backup.runner.Result(channel = 'CXXX1', directory = 'general', messages = 6, deleted = 1, withheld = 0, files = 0, failures = 0)
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

    assert results[1] == threadvault.backup.runner.Result(channel = 'CXXX1', directory = 'general', messages = 5, deleted = 0, withheld = 1, files = 0, failures = 0)

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

    assert results[1] == threadvault.backup.runner.Result(channel = 'CXXX1', directory = 'general', messages = 5, deleted = 0, withheld = 0, files = 0, failures = 0)

def test_runner_vault_selection(
    tmp_path: pathlib.Path,
    slack: slack_sdk.web.WebClient
) -> None:

    results = run(slack, tmp_path, dataclasses.replace(SETTINGS, channel_mode = 'selected', channels_selected = ('CXXX2',)))

    assert [result.channel for result in results] == ['CXXX2']
    assert [channel['id'] for channel in read(tmp_path, 'groups.json')] == ['CXXX2']
    assert read(tmp_path, 'channels.json') == []
    assert threadvault.vault.state.load(tmp_path) == {'CXXX2': 'xxx'}

def test_runner_vault_backlog(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'clone'))

    with respx.mock:

        respx.get(REPOSITORY).respond(200, json = {'clone_url': str(remote), 'full_name': 'xxx/xxx', 'private': True})
        respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'id': 1, 'login': 'xxx'})

        publish(slack, directory)

        workspace['messages']['CXXX1'] += [REPLY_THREAD]

        publish(slack, directory)

        assert not pathlib.Path(os.path.join(directory, 'raw', 'general', '2026-10-05.json')).exists()

        results, _ = publish(slack, directory, BACKLOG_THREAD)

    assert [message['ts'] for message in read(directory, 'general', '2026-10-05.json')] == ['1791158400.000000']
    assert results[1].messages == 6

def test_runner_vault_attachment(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    workspace['messages']['CXXX1'] += [{'files': ATTACHMENT_CONTENT, 'text': '', 'ts': '1791158400.000000', 'type': 'message', 'user': 'UXXX1'}]
    transcript = pathlib.Path(os.path.join(tmp_path, 'transcripts', 'general', '2026-10.md'))

    with respx.mock: results = run(slack, tmp_path, dataclasses.replace(SETTINGS, attachments_enabled = False))

    assert (results[1].files, results[1].failures) == (0, 0)
    assert transcript.read_text(encoding = 'utf-8').splitlines()[-3:] == [f'- [xxx.txt]({file['permalink']})' for file in ATTACHMENT_CONTENT]

    with respx.mock:

        respx.get('https://files.slack.com/xxx1').respond(200, content = b'xxx', headers = {'content-type': 'text/plain'})
        respx.get('https://files.slack.com/xxx2').respond(200, content = b'xxx', headers = {'content-type': 'text/html'})
        results = run(slack, tmp_path)

    assert (results[1].files, results[1].failures) == (1, 1)
    assert survey(pathlib.Path(os.path.join(tmp_path, 'attachments'))) == ['2026-10/FXXX1/xxx.txt']
    assert transcript.read_text(encoding = 'utf-8').splitlines()[-3:] == ATTACHMENT_LINK

    with respx.mock:

        respx.get('https://files.slack.com/xxx2').respond(200, content = b'xxx', headers = {'content-type': 'text/html'})
        results = run(slack, tmp_path)

    assert (results[1].files, results[1].failures) == (0, 1)

def test_runner_vault_interruption(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    slack: slack_sdk.web.WebClient
) -> None:

    history = threadvault.slack.api.history

    def interrupt(
        client: slack_sdk.web.WebClient,
        channel: str,
        *,
        oldest: str,
        latest: str
    ) -> list[dict[str, typing.Any]]:

        if channel == 'CXXX1': raise ConnectionError

        return history(client, channel, oldest = oldest, latest = latest)

    monkeypatch.setattr(threadvault.slack.api, 'history', interrupt)

    with pytest.raises(ConnectionError): run(slack, tmp_path)

    assert threadvault.vault.state.load(tmp_path) == {'CXXX2': 'xxx'}

def test_runner_vault_checkpoint(
    tmp_path: pathlib.Path,
    slack: slack_sdk.web.WebClient
) -> None:

    states = []

    for _ in range(2): threadvault.backup.runner.run(slack, tmp_path, SETTINGS, days = 30, limit = None, now = NOW, checkpoint = lambda _: states.append(threadvault.vault.state.load(tmp_path)))

    assert states == [{'CXXX2': 'xxx'}, {'CXXX1': 'general', 'CXXX2': 'xxx'}]

def test_runner_vault_resynchronisation(
    tmp_path: pathlib.Path,
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    directories = []

    run(slack, tmp_path)

    workspace['messages']['CXXX1'] = [message for message in workspace['messages']['CXXX1'] if message['ts'] not in MESSAGES_DELETION]

    results = threadvault.backup.runner.run(slack, tmp_path, SETTINGS, days = None, limit = None, now = NOW, checkpoint = lambda result: directories.append(result.directory))

    assert directories == ['xxx', 'general']
    assert [(result.messages, result.deleted, result.withheld) for result in results] == [(0, 0, 0), (5, 0, 1)]

def test_runner_vault_publication(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    git: collections.abc.Callable[..., str],
    slack: slack_sdk.web.WebClient
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'clone'))
    found = httpx.Response(200, json = {'clone_url': str(remote), 'full_name': 'xxx/xxx', 'private': True})

    with respx.mock:

        respx.get(REPOSITORY).mock(side_effect = [httpx.Response(404, json = {'message': 'Not Found'}), *[found] * 9])
        creation = respx.post(f'{threadvault.github.rest.API_URL}/user/repos').respond(201, json = {'clone_url': str(remote), 'full_name': 'xxx/xxx', 'private': True})
        respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'id': 1, 'login': 'xxx'})
        results, commit = publish(slack, directory)
        log = git('log', '--format=%s %ae', 'main', directory = remote).splitlines()
        publish(slack, directory)

    assert creation.call_count == 1
    assert [result.messages for result in results] == [0, 5]
    assert commit == git('rev-parse', 'main', directory = remote).strip()
    assert log == ['Back up at 2026-10-05 01:00 UTC 1+xxx@users.noreply.github.com', 'Back up #general 1+xxx@users.noreply.github.com', 'Back up #xxx 1+xxx@users.noreply.github.com', 'xxx xxx@xxx.xxx']
    assert git('log', '--format=%s', 'main', directory = remote).splitlines() == [line.rpartition(' ')[0] for line in log]
    assert git('ls-tree', '-r', '--name-only', 'main', directory = remote).splitlines() == FILES_PUBLISHED
    assert git('show', 'main:README.md', directory = remote).splitlines()[0] == '# Slack のバックアップ'

def test_runner_vault_privacy(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    git: collections.abc.Callable[..., str],
    slack: slack_sdk.web.WebClient
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'clone'))

    with respx.mock:

        respx.get(REPOSITORY).respond(200, json = {'clone_url': str(remote), 'full_name': 'xxx/xxx', 'private': False})

        with pytest.raises(threadvault.backup.runner.VaultError, match = 'is public'): publish(slack, directory)

    assert not directory.exists()
    assert git('log', '--format=%s', 'main', directory = remote).splitlines() == ['xxx']

def test_runner_vault_exposure(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    git: collections.abc.Callable[..., str],
    slack: slack_sdk.web.WebClient
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'clone'))
    responses = [httpx.Response(200, json = {'clone_url': str(remote), 'full_name': 'xxx/xxx', 'private': private}) for private in (True, False)]

    with respx.mock:

        respx.get(REPOSITORY).mock(side_effect = responses)
        respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'id': 1, 'login': 'xxx'})

        with pytest.raises(threadvault.backup.runner.VaultError, match = 'no longer a private repository'): publish(slack, directory)

    assert git('log', '--format=%s', 'main', directory = remote).splitlines() == ['xxx']

def test_runner_vault_lock(
    tmp_path: pathlib.Path,
    slack: slack_sdk.web.WebClient
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'clone'))

    with threadvault.backup.runner.hold(directory), pytest.raises(threadvault.backup.runner.LockError, match = 'already writing'): publish(slack, directory)
    with threadvault.backup.runner.hold(directory), pytest.raises(threadvault.backup.runner.LockError, match = 'already writing'), threadvault.backup.runner.hold(directory): pass
    with threadvault.backup.runner.hold(directory), threadvault.backup.runner.hold(pathlib.Path(os.path.join(tmp_path, 'xxx'))): pass

    assert not directory.exists()

def test_runner_vault_git(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    slack: slack_sdk.web.WebClient
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'clone'))
    monkeypatch.setattr(threadvault.vault.repository, 'VERSION_MINIMUM', (999, 0))

    with respx.mock, pytest.raises(threadvault.vault.repository.GitError, match = 'or newer is needed'): publish(slack, directory)

    assert not directory.exists()
