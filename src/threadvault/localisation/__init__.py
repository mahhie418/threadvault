"""Messages of the Slack app in English and Japanese."""

import functools
import importlib.resources
import json

import threadvault.configuration

def choose(
    locale: str | None,
    default: threadvault.configuration.Language
) -> threadvault.configuration.Language:

    """Chooses the language of a Slack user.

    Args:
        locale: Slack locale of the user, such as ja-JP, or None when unknown.
        default: Language for a locale that has no messages.

    Returns:
        The language.
    """

    if locale is None: return default
    if locale.startswith('ja'): return 'ja'
    if locale.startswith('en'): return 'en'

    return default

def translate(
    key: str,
    language: threadvault.configuration.Language
) -> str:

    """Gives a message in a language.

    Args:
        key: Key of the message, such as home.github.
        language: The language.

    Returns:
        The message.
    """

    return _messages(language)[key]

@functools.cache
def _messages(
    language: threadvault.configuration.Language
) -> dict[str, str]:

    return json.loads(importlib.resources.files('threadvault.localisation').joinpath(f'{language}.json').read_text(encoding = 'utf-8'))
