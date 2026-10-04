"""AI-friendly Markdown made from the messages in the vault."""

import collections.abc
import re

_PATTERN_CONTENT = re.compile(r'(```.*?```|`[^`\n]*`|<[^<>\n]*>)', re.DOTALL)
_PATTERN_BOLD = re.compile(r'(?<![A-Za-z0-9*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![A-Za-z0-9*])')
_PATTERN_STRIKETHROUGH = re.compile(r'(?<![A-Za-z0-9~])~(?=\S)([^~\n]+?)(?<=\S)~(?![A-Za-z0-9~])')
_PATTERN_BLANK = re.compile(r'\n{3,}')

_MENTION_CATEGORY = frozenset({'everyone', 'channel', 'here'})

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
