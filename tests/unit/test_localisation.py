# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import importlib.resources
import json
import string

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

    translations = [json.loads(importlib.resources.files('threadvault.localisation').joinpath(f'{language}.json').read_text(encoding = 'utf-8')) for language in ('en', 'ja')]
    placeholders = [{key: {name for _, name, _, _ in string.Formatter().parse(message) if name} for key, message in translation.items()} for translation in translations]

    assert placeholders[0] == placeholders[1]

@pytest.mark.parametrize(('locale', 'default', 'expected'), LOCALES_CHOSEN)
def test_localisation_locale_choice(
    locale: str | None,
    default: threadvault.configuration.Language,
    expected: threadvault.configuration.Language
) -> None:

    assert threadvault.localisation.choose(locale, default) == expected

def test_localisation_message_translation() -> None:

    assert [threadvault.localisation.translate('home.destination', language) for language in ('en', 'ja')] == ['Destination', '保存先']
