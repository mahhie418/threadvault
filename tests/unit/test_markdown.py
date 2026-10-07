import json
import os
import pathlib
import typing

import pytest

import threadvault.configuration
import threadvault.vault.markdown

DIRECTORIES = {'CXXX1': 'general', 'CXXX2': 'xxx'}
NAMES = {'UXXX1': 'xxx1', 'CXXX1': 'general'}
URL = 'https://xxx.slack.com/'

READMES_INTRODUCED = [
    ('', 'en', '# Slack backup'),
    ('', 'ja', '# Slack のバックアップ'),
    ('# xxx', 'en', '# Slack backup'),
    ('xxx', 'en', 'xxx')
]

MONTHS_SPLIT = [('Asia/Tokyo', ['2023-11.md']), ('UTC', ['2023-10.md'])]

FILES_ATTACHED = [
    {'id': 'FXXX1', 'name': 'xxx1.txt', 'permalink': 'https://xxx.slack.com/files/UXXX2/FXXX1/xxx1.txt'},
    {'id': 'FXXX2', 'name': 'xxx 2.txt', 'permalink': 'https://xxx.slack.com/files/UXXX2/FXXX2/xxx_2.txt'},
    {'id': 'FXXX3', 'mode': 'tombstone'}
]

TEXTS_CORRESPONDENCE = [
    ('xxx', 'xxx'),
    ('&lt;xxx&gt; &amp;lt;', '<xxx> &lt;'),
    ('<@UXXX1> <@UXXX2|xxx2> <@UXXX3>', '@xxx1 @xxx2 @UXXX3'),
    ('<#CXXX1|xxx> <#CXXX2|xxx2> <#CXXX3>', '#general #xxx2 #CXXX3'),
    ('<!everyone> <!channel> <!here>', '@everyone @channel @here'),
    ('<!subteam^SXXX|@xxx> <!date^1000000000^{date}|xxx>', '@xxx xxx'),
    ('<https://xxx.xxx/?a=1&amp;b=2|xxx>', '[xxx](https://xxx.xxx/?a=1&b=2)'),
    ('<https://xxx.xxx/> <https://xxx.xxx/|https://xxx.xxx/>', '<https://xxx.xxx/> <https://xxx.xxx/>'),
    ('<mailto:xxx@xxx.xxx|xxx@xxx.xxx>', '[xxx@xxx.xxx](mailto:xxx@xxx.xxx)'),
    ('*xxx* *xxx xxx* テスト*テスト*テスト', '**xxx** **xxx xxx** テスト**テスト**テスト'),
    ('1*2*3 * xxx', '1*2*3 * xxx'),
    ('~xxx~ _xxx_', '~~xxx~~ _xxx_'),
    ('`*xxx* &lt;`', '`*xxx* <`'),
    ('xxx```*xxx*\n&lt;xxx&gt;```xxx', 'xxx\n```\n*xxx*\n<xxx>\n```\nxxx'),
    ('&gt; xxx\nxxx', '> xxx\nxxx')
]

def locate(
    *names: str
) -> pathlib.Path:

    return pathlib.Path(os.path.join(pathlib.Path(__file__).parents[1], 'fixtures', *names))

def render(
    directory: pathlib.Path,
    messages: list[dict[str, typing.Any]],
    timezone: str,
    language: threadvault.configuration.Language,
    attachments: dict[str, str] | None = None
) -> None:

    users = json.loads(locate('slack', 'users.list.json').read_text(encoding = 'utf-8'))
    channels = json.loads(locate('slack', 'conversations.list.json').read_text(encoding = 'utf-8'))
    channel = next(entry for entry in channels if entry['id'] == 'CXXX1')

    threadvault.vault.markdown.transcribe(directory, channel, messages, users = users, channels = channels, attachments = attachments or {}, url = URL, timezone = timezone, language = language)

@pytest.mark.parametrize(('text', 'expected'), TEXTS_CORRESPONDENCE)
def test_markdown_text_conversion(
    text: str,
    expected: str
) -> None:

    assert threadvault.vault.markdown.convert(text, NAMES) == expected

def test_markdown_message_export(
    tmp_path: pathlib.Path
) -> None:

    messages = json.loads(locate('slack', 'messages.json').read_text(encoding = 'utf-8'))
    render(tmp_path, messages, 'Asia/Tokyo', 'ja')
    names = sorted(entry.name for entry in tmp_path.iterdir())

    assert names == sorted(entry.name for entry in locate('vault', 'transcripts', 'general').iterdir())
    for name in names: assert pathlib.Path(os.path.join(tmp_path, name)).read_bytes() == locate('vault', 'transcripts', 'general', name).read_bytes()

def test_markdown_message_time(
    tmp_path: pathlib.Path
) -> None:

    messages = json.loads(locate('slack', 'messages.json').read_text(encoding = 'utf-8'))
    render(tmp_path, messages, 'UTC', 'en')
    lines = pathlib.Path(os.path.join(tmp_path, '2017-11.md')).read_text(encoding = 'utf-8').splitlines()
    reply = next(index for index, line in enumerate(lines) if line.startswith('####'))

    assert lines.index('## 2017-11-17 (Fri)') < reply
    assert lines[reply].startswith('#### [2026-10-04 00:00]')

def test_markdown_message_removal(
    tmp_path: pathlib.Path
) -> None:

    messages = json.loads(locate('slack', 'messages.json').read_text(encoding = 'utf-8'))
    render(tmp_path, messages, 'Asia/Tokyo', 'ja')
    render(tmp_path, [message for message in messages if message['ts'] in {'1510880400.000000', '1510963199.000000'}], 'Asia/Tokyo', 'ja')

    assert [entry.name for entry in tmp_path.iterdir()] == ['2017-11.md']

@pytest.mark.parametrize(('timezone', 'names'), MONTHS_SPLIT)
def test_markdown_message_timezone(
    tmp_path: pathlib.Path,
    timezone: str,
    names: list[str]
) -> None:

    render(tmp_path, [{'text': 'xxx', 'ts': '1698795000.000000', 'user': 'UXXX2'}], timezone, 'en')

    assert [entry.name for entry in tmp_path.iterdir()] == names

def test_markdown_reply_orphan(
    tmp_path: pathlib.Path
) -> None:

    render(tmp_path, [{'text': 'xxx', 'thread_ts': '1700006399.000000', 'ts': '1700006400.000000', 'user': 'UXXX2'}], 'UTC', 'en')
    lines = pathlib.Path(os.path.join(tmp_path, '2023-11.md')).read_text(encoding = 'utf-8').splitlines()

    assert lines[4].startswith('### [00:00]')

def test_markdown_file_link(
    tmp_path: pathlib.Path
) -> None:

    render(tmp_path, [{'files': FILES_ATTACHED, 'text': '', 'ts': '1700006400.000000', 'user': 'UXXX2'}], 'UTC', 'en', {'FXXX2': 'attachments/2023-11/FXXX2/xxx 2.txt'})
    lines = pathlib.Path(os.path.join(tmp_path, '2023-11.md')).read_text(encoding = 'utf-8').splitlines()

    assert lines[-3:] == ['', '- [xxx1.txt](https://xxx.slack.com/files/UXXX2/FXXX1/xxx1.txt)', '- [xxx 2.txt](../../attachments/2023-11/FXXX2/xxx%202.txt)']

@pytest.mark.parametrize(('existing', 'language', 'expected'), READMES_INTRODUCED)
def test_markdown_readme_introduction(
    tmp_path: pathlib.Path,
    existing: str,
    language: threadvault.configuration.Language,
    expected: str
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, threadvault.vault.markdown.README_FILE))

    if existing: path.write_text(existing, encoding = 'utf-8')

    threadvault.vault.markdown.introduce(tmp_path, 'xxx', language = language)

    assert path.read_text(encoding = 'utf-8').splitlines()[0] == expected

def test_markdown_index_japanese(
    tmp_path: pathlib.Path
) -> None:

    channels = json.loads(locate('slack', 'conversations.list.json').read_text(encoding = 'utf-8'))
    threadvault.vault.markdown.catalogue(tmp_path, channels, DIRECTORIES, timezone = 'Asia/Tokyo', language = 'ja')
    file = pathlib.Path(os.path.join(tmp_path, 'transcripts', threadvault.vault.markdown.INDEX_FILE))

    assert file.read_bytes() == locate('vault', 'transcripts', 'index.md').read_bytes()

def test_markdown_index_english(
    tmp_path: pathlib.Path
) -> None:

    channels = json.loads(locate('slack', 'conversations.list.json').read_text(encoding = 'utf-8'))
    threadvault.vault.markdown.catalogue(tmp_path, channels, DIRECTORIES, timezone = 'UTC', language = 'en')
    lines = pathlib.Path(os.path.join(tmp_path, 'transcripts', threadvault.vault.markdown.INDEX_FILE)).read_text(encoding = 'utf-8').splitlines()

    assert lines[-4:] == ['## Channels', '', '- [#general](general/)', '- [#xxx](xxx/)']
