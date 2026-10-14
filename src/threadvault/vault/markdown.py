# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""AI-friendly Markdown made from the messages in the vault."""

import collections
import collections.abc
import datetime
import decimal
import importlib.resources
import itertools
import os
import pathlib
import re
import typing
import urllib.parse
import zoneinfo

import threadvault.configuration
import threadvault.product
import threadvault.vault.export
import threadvault.vault.files
import threadvault.vault.state

TRANSCRIPTS_DIRECTORY = 'transcripts'

README_FILE = 'README.md'
INDEX_FILE = 'index.md'

_PATTERN_CONTENT = re.compile(r'(```.*?```|`[^`\n]*`|<[^<>\n]*>)', re.DOTALL)
_PATTERN_BOLD = re.compile(r'(?<![A-Za-z0-9*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![A-Za-z0-9*])')
_PATTERN_STRIKETHROUGH = re.compile(r'(?<![A-Za-z0-9~])~(?=\S)([^~\n]+?)(?<=\S)~(?![A-Za-z0-9~])')
_PATTERN_BLANK = re.compile(r'\n{3,}')

_MENTION_CATEGORY = frozenset({'everyone', 'channel', 'here'})

_WEEKDAYS: dict[threadvault.configuration.Language, tuple[str, ...]] = {
    'en': ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'),
    'ja': ('月', '火', '水', '木', '金', '土', '日')
}

def convert(
    text: str,
    names: collections.abc.Mapping[str, str]
) -> str:

    """Converts the mrkdwn of a Slack message to Markdown.

    Mentions become names, links become Markdown links, bold and
    strikethrough take the Markdown markers, and code blocks get fences on
    lines of their own. Code keeps its content. The escapes &amp;, &lt; and
    &gt; turn back into characters.

    Args:
        text: Text of the message.
        names: Names by user and channel ID.

    Returns:
        The Markdown.
    """

    contents = _PATTERN_CONTENT.split(text)
    markdown = ''.join(_translate(piece, names) if index % 2 else _format(piece) for index, piece in enumerate(contents))

    return _PATTERN_BLANK.sub('\n\n', markdown).strip('\n')

def transcribe(
    directory: pathlib.Path,
    channel: collections.abc.Mapping[str, typing.Any],
    messages: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    *,
    users: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    channels: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    attachments: collections.abc.Mapping[str, str],
    url: str,
    timezone: str,
    language: threadvault.configuration.Language
) -> None:

    """Writes the Markdown of a channel, one file a month.

    A message goes to the file of the month in which it was posted, in
    `timezone`, under a heading for its day. Times show their offset from
    UTC, which tells apart the hour that repeats when daylight saving time
    ends. Thread replies follow their parent, whenever they were posted; a
    reply whose parent is not given stands on its own. Each message links to
    Slack, and so does each of its attached files, unless the vault holds a
    copy to link to instead. Each file holds the given messages of its month
    and replaces the file that was there, and the file of a month without
    messages is removed, so give every message of the channel.

    Args:
        directory: Directory of the channel among the Markdown files.
        channel: The channel as conversations.list returns it.
        messages: Messages of the channel, each once, as conversations.history
                  and conversations.replies return them.
        users: Users as users.list returns them.
        channels: Channels as conversations.list returns them, for mentions.
        attachments: Paths in the vault of the attached files that it holds,
                     by file ID.
        url: Address of the workspace, as auth.test returns it.
        timezone: IANA time zone for the months, days and times.
        language: Language of the day headings.
    """

    names = {user['id']: _name(user) for user in users} | {channel['id']: channel['name'] for channel in channels}
    zone = zoneinfo.ZoneInfo(timezone)
    ordered = sorted(messages, key = lambda message: decimal.Decimal(message['ts']))
    timestamps = {message['ts'] for message in ordered}
    replies: dict[str, list[collections.abc.Mapping[str, typing.Any]]] = collections.defaultdict(list)
    months: dict[str, list[collections.abc.Mapping[str, typing.Any]]] = collections.defaultdict(list)

    for message in ordered:

        thread_ts = message.get('thread_ts', message['ts'])
        month = _localise(message, zone).strftime('%Y-%m')

        (replies[thread_ts] if thread_ts != message['ts'] and thread_ts in timestamps else months[month]).append(message)

    directory.mkdir(parents = True, exist_ok = True)

    for month, parents in months.items():

        lines = [f'# #{channel['name']} {month}']

        for day, group in itertools.groupby(parents, key = lambda message: _localise(message, zone).date()):

            lines += ['', f'## {day.isoformat()} ({_WEEKDAYS[language][day.weekday()]})']

            for parent in group:

                lines += _render(parent, '###', day, channel['id'], url, zone, names, attachments)

                for reply in replies[parent['ts']]: lines += _render(reply, '####', day, channel['id'], url, zone, names, attachments)

        text = '\n'.join(lines)

        pathlib.Path(os.path.join(directory, f'{month}.md')).write_text(f'{text}\n', encoding = 'utf-8', newline = '\n')

    stale = [path for path in directory.glob('*.md') if path.stem not in months]

    for path in stale: path.unlink()

def catalogue(
    vault: pathlib.Path,
    channels: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    directories: collections.abc.Mapping[str, str],
    *,
    timezone: str,
    language: threadvault.configuration.Language
) -> None:

    """Writes the index of the Markdown files.

    The index tells how the vault is laid out and which version of the
    format it follows, and links to the Markdown of each channel.

    Args:
        vault: Root directory of the vault.
        channels: Channels to list, as conversations.list returns them.
        directories: Directory names by channel ID.
        timezone: IANA time zone of the Markdown files.
        language: Language of the index.
    """

    template = importlib.resources.files('threadvault.vault').joinpath('templates', f'index.{language}.md').read_text(encoding = 'utf-8')

    introduction = template.format(
        product = threadvault.product.NAME,
        version = threadvault.vault.state.FORMAT_VERSION,
        raw = threadvault.vault.export.RAW_DIRECTORY,
        users = threadvault.vault.export.USERS_FILE,
        channels = threadvault.vault.export.CHANNELS_FILE,
        groups = threadvault.vault.export.GROUPS_FILE,
        transcripts = TRANSCRIPTS_DIRECTORY,
        attachments = threadvault.vault.files.ATTACHMENTS_DIRECTORY,
        timezone = timezone
    )

    entries = [f'- [#{channel['name']}]({directories[channel['id']]}/)' for channel in sorted(channels, key = lambda channel: channel['name'])]
    text = '\n'.join([introduction, *entries])
    path = pathlib.Path(os.path.join(vault, TRANSCRIPTS_DIRECTORY, INDEX_FILE))
    path.parent.mkdir(exist_ok = True)
    path.write_text(f'{text}\n', encoding = 'utf-8', newline = '\n')

def introduce(
    vault: pathlib.Path,
    name: str,
    *,
    language: threadvault.configuration.Language
) -> None:

    """Writes the README of the vault, unless the vault has one of its own.

    The README that GitHub puts into a new repository, a heading with the
    name of the repository, is replaced; any other README is kept.

    Args:
        vault: Root directory of the vault.
        name: Name of the repository of the vault.
        language: Language of the README.
    """

    path = pathlib.Path(os.path.join(vault, README_FILE))

    if path.exists() and path.read_text(encoding = 'utf-8').strip() != f'# {name}': return

    template = importlib.resources.files('threadvault.vault').joinpath('templates', f'readme.{language}.md').read_text(encoding = 'utf-8')

    path.write_text(template.format(product = threadvault.product.NAME, transcripts = TRANSCRIPTS_DIRECTORY, index = INDEX_FILE), encoding = 'utf-8', newline = '\n')

def _unescape(
    text: str
) -> str:

    return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

def _format(
    text: str
) -> str:

    return _PATTERN_STRIKETHROUGH.sub(r'~~\1~~', _PATTERN_BOLD.sub(r'**\1**', _unescape(text)))

def _translate(
    piece: str,
    names: collections.abc.Mapping[str, str]
) -> str:

    if piece.startswith('```'): return f'\n```\n{_unescape(piece[3:-3]).strip('\n')}\n```\n'
    if piece.startswith('`'): return _unescape(piece)

    target, _, label = piece[1:-1].partition('|')
    label = _unescape(label)
    url = _unescape(target)

    match target[:1]:

        case '@': return f'@{names.get(target[1:]) or label or target[1:]}'
        case '#': return f'#{names.get(target[1:]) or label or target[1:]}'
        case '!': return f'@{target[1:]}' if target[1:] in _MENTION_CATEGORY else label or target[1:]
        case _: return f'<{url}>' if label in {'', url} else f'[{label}]({url})'

def _name(
    user: collections.abc.Mapping[str, typing.Any]
) -> str:

    profile: collections.abc.Mapping[str, str] = user.get('profile', {})

    return profile.get('display_name') or profile.get('real_name') or user.get('name') or user['id']

def _localise(
    message: collections.abc.Mapping[str, typing.Any],
    zone: zoneinfo.ZoneInfo
) -> datetime.datetime:

    return datetime.datetime.fromtimestamp(float(message['ts']), zone)

def _render(
    message: collections.abc.Mapping[str, typing.Any],
    marks: str,
    day: datetime.date,
    channel: str,
    url: str,
    zone: zoneinfo.ZoneInfo,
    names: collections.abc.Mapping[str, str],
    attachments: collections.abc.Mapping[str, str]
) -> list[str]:

    time = _localise(message, zone)
    label = time.strftime('%H:%M %:z' if time.date() == day else '%Y-%m-%d %H:%M %:z')
    link = f'{url.rstrip('/')}/archives/{channel}/p{typing.cast(str, message['ts']).replace('.', '')}'
    author = names.get(message.get('user', '')) or message.get('username') or message.get('user') or message.get('bot_id', '')
    text = convert(message.get('text', ''), names)
    files = [_attach(file, attachments) for file in message.get('files', []) if 'name' in file]

    if message.get('thread_ts', message['ts']) != message['ts']: link += f'?thread_ts={message['thread_ts']}&cid={channel}'

    return ['', f'{marks} [{label}]({link}) {author}'] + (['', text] if text else []) + (['', *files] if files else [])

def _attach(
    file: collections.abc.Mapping[str, typing.Any],
    attachments: collections.abc.Mapping[str, str]
) -> str:

    if file['id'] in attachments: return f'- [{file['name']}](../../{urllib.parse.quote(attachments[file['id']])})'

    return f'- [{file['name']}]({file['permalink']})' if 'permalink' in file else f'- {file['name']}'
