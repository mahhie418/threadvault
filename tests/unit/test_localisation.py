import importlib.resources
import json

import pytest

import threadvault.configuration
import threadvault.localisation

LOCALES_CHOSEN = [
    ('ja-JP', 'en', 'ja'),
    ('en-GB', 'ja', 'en'),
    ('fr-FR', 'ja', 'ja'),
    (None, 'en', 'en')
]

def test_localisation_key_consistency() -> None:

    keys = [set(json.loads(importlib.resources.files('threadvault.localisation').joinpath(f'{language}.json').read_text(encoding = 'utf-8'))) for language in ('en', 'ja')]

    assert keys[0] == keys[1]

@pytest.mark.parametrize(('locale', 'default', 'expected'), LOCALES_CHOSEN)
def test_localisation_locale_choice(
    locale: str | None,
    default: threadvault.configuration.Language,
    expected: threadvault.configuration.Language
) -> None:

    assert threadvault.localisation.choose(locale, default) == expected

def test_localisation_message_translation() -> None:

    assert [threadvault.localisation.translate('home.destination', language) for language in ('en', 'ja')] == ['Destination', '保存先']
