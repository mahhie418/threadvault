import os
import pathlib

import platformdirs
import pytest

import threadvault.configuration
import threadvault.product

PREFIXES = ('THREADVAULT_', 'SLACK_', 'GITHUB_APP_')

ENVIRONMENT_VALID = {
    'SLACK_BOT_TOKEN': 'xoxb-xxx',
    'SLACK_APP_TOKEN': 'xapp-xxx',
    'GITHUB_APP_CLIENT_ID': 'xxx',
    'GITHUB_APP_SLUG': 'xxx',
    'THREADVAULT_OWNER_ID': ' UXXX ',
    'THREADVAULT_ADMIN_IDS': ' UXXX , WXXX ,, ',
    'THREADVAULT_SECRET_KEY': 'xxx',
    'THREADVAULT_LANGUAGE_DISPLAY': 'JA',
    'THREADVAULT_LOOKBACK_DAYS': '90',
    'THREADVAULT_DELETIONS_MAXIMUM': '0'
}

ENVIRONMENT_INVALID = [
    ('SLACK_BOT_TOKEN', 'xapp-xxx', 'SLACK_BOT_TOKEN'),
    ('SLACK_APP_TOKEN', 'xoxb-xxx', 'SLACK_APP_TOKEN'),
    ('GITHUB_APP_CLIENT_ID', 'xxx xxx', 'GITHUB_APP_CLIENT_ID'),
    ('GITHUB_APP_SLUG', 'xxx_xxx', 'GITHUB_APP_SLUG'),
    ('THREADVAULT_OWNER_ID', 'UXXX,WXXX', 'THREADVAULT_OWNER_ID'),
    ('THREADVAULT_ADMIN_IDS', 'UXXX,xxx', 'xxx'),
    ('THREADVAULT_LANGUAGE_DISPLAY', 'xxx', 'THREADVAULT_LANGUAGE_DISPLAY'),
    ('THREADVAULT_LOOKBACK_DAYS', '0', 'between 1 and 90'),
    ('THREADVAULT_LOOKBACK_DAYS', str(threadvault.configuration.LOOKBACK_DAYS_MAXIMUM + 1), 'between 1 and 90'),
    ('THREADVAULT_LOOKBACK_DAYS', 'xxx', 'must be an integer'),
    ('THREADVAULT_DELETIONS_MAXIMUM', '-1', 'at least 0')
]

@pytest.fixture
def isolated(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:

    monkeypatch.chdir(tmp_path)

    for name in [name for name in os.environ if name.startswith(PREFIXES)]: monkeypatch.delenv(name)

    return tmp_path

def test_configuration_values_default() -> None:

    settings = threadvault.configuration.load({})

    assert not settings.slack_bot_token
    assert not settings.slack_app_token
    assert not settings.threadvault_owner_id
    assert settings.threadvault_admin_ids == frozenset()
    assert settings.threadvault_secret_key is None
    assert settings.threadvault_data_directory == platformdirs.user_data_path(threadvault.product.NAME, appauthor = False)
    assert settings.threadvault_language_display == 'en'
    assert settings.threadvault_lookback_days == threadvault.configuration.LOOKBACK_DAYS_DEFAULT
    assert settings.threadvault_deletions_maximum is None

def test_configuration_values_parse() -> None:

    settings = threadvault.configuration.load(ENVIRONMENT_VALID)

    assert settings.slack_bot_token == ENVIRONMENT_VALID['SLACK_BOT_TOKEN']
    assert settings.slack_app_token == ENVIRONMENT_VALID['SLACK_APP_TOKEN']
    assert settings.github_app_client_id == ENVIRONMENT_VALID['GITHUB_APP_CLIENT_ID']
    assert settings.github_app_slug == ENVIRONMENT_VALID['GITHUB_APP_SLUG']
    assert settings.threadvault_owner_id == 'UXXX'
    assert settings.threadvault_admin_ids == frozenset({'UXXX', 'WXXX'})
    assert settings.threadvault_secret_key == ENVIRONMENT_VALID['THREADVAULT_SECRET_KEY']
    assert settings.threadvault_language_display == 'ja'
    assert settings.threadvault_lookback_days == 90
    assert settings.threadvault_deletions_maximum == 0

@pytest.mark.parametrize(('name', 'value', 'expected'), ENVIRONMENT_INVALID)
def test_configuration_values_invalid(
    name: str,
    value: str,
    expected: str
) -> None:

    with pytest.raises(threadvault.configuration.ConfigurationError, match = expected): threadvault.configuration.load({name: value})

def test_configuration_values_secure() -> None:

    with pytest.raises(threadvault.configuration.ConfigurationError) as exception: threadvault.configuration.load({'SLACK_BOT_TOKEN': 'xapp-xxx'})

    assert 'xapp-xxx' not in str(exception.value)

def test_configuration_values_present() -> None:

    settings = threadvault.configuration.load(ENVIRONMENT_VALID)
    settings.require('slack_bot_token', 'slack_app_token', 'github_app_client_id', 'github_app_slug', 'threadvault_owner_id', 'threadvault_admin_ids')

def test_configuration_values_missing() -> None:

    settings = threadvault.configuration.load({'SLACK_BOT_TOKEN': ENVIRONMENT_VALID['SLACK_BOT_TOKEN']})
    expected = r': SLACK_APP_TOKEN, THREADVAULT_ADMIN_IDS$'

    with pytest.raises(threadvault.configuration.ConfigurationError, match = expected): settings.require('slack_bot_token', 'slack_app_token', 'threadvault_admin_ids')

def test_configuration_directory_home() -> None:

    settings = threadvault.configuration.load({'THREADVAULT_DATA_DIRECTORY': '~/xxx'})
    expected = pathlib.Path('~/xxx').expanduser().resolve()

    assert settings.threadvault_data_directory == expected

def test_configuration_directory_relative(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.chdir(tmp_path)

    settings = threadvault.configuration.load({'THREADVAULT_DATA_DIRECTORY': 'xxx'})
    expected = pathlib.Path(os.path.join(tmp_path, 'xxx')).resolve()

    assert settings.threadvault_data_directory == expected

def test_configuration_dotenv_reading(
    isolated: pathlib.Path
) -> None:

    file = pathlib.Path(os.path.join(isolated, '.env'))
    file.write_text('THREADVAULT_LANGUAGE_DISPLAY=ja\n', encoding = 'utf-8')

    settings = threadvault.configuration.load()

    assert settings.threadvault_language_display == 'ja'

def test_configuration_dotenv_override(
    isolated: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    file = pathlib.Path(os.path.join(isolated, '.env'))
    file.write_text('THREADVAULT_LOOKBACK_DAYS=0\n', encoding = 'utf-8')

    monkeypatch.setenv('THREADVAULT_LOOKBACK_DAYS', '90')
    settings = threadvault.configuration.load()

    assert settings.threadvault_lookback_days == 90

@pytest.mark.usefixtures('isolated')
def test_configuration_dotenv_missing(
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setenv('THREADVAULT_DELETIONS_MAXIMUM', '7')
    settings = threadvault.configuration.load()

    assert settings.threadvault_deletions_maximum == 7
