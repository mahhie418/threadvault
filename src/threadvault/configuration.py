"""Configuration read from environment variables and an optional .env file."""

import collections.abc
import dataclasses
import itertools
import os
import pathlib
import re
import typing

import dotenv
import platformdirs

import threadvault.product

type Language = typing.Literal['en', 'ja']
type FieldRequired = typing.Literal['slack_bot_token', 'slack_app_token', 'github_app_client_id', 'github_app_slug', 'threadvault_owner_id', 'threadvault_admin_ids']

_PATTERN_GITHUB_APP_CLIENT_ID = re.compile(r'[A-Za-z0-9.]+')
_PATTERN_GITHUB_APP_SLUG = re.compile(r'[a-z0-9][a-z0-9-]*')
_PATTERN_SLACK_USER_ID = re.compile(r'[UW][A-Z0-9]{2,}')

LOOKBACK_DAYS_DEFAULT = 30
LOOKBACK_DAYS_MAXIMUM = 90

class ConfigurationError(Exception):

    """Raised when the environment does not describe a usable configuration."""

@dataclasses.dataclass(frozen = True, kw_only = True, slots = True)
class Settings:

    """Validated settings for one deployment.

    Credentials that only some commands need are empty strings when unset.
    Commands call `require` before using them, so that every missing variable
    is reported at once.

    Attributes:
        slack_bot_token: Slack bot token (xoxb-...).
        slack_app_token: Slack app-level token (xapp-...) for Socket Mode.
        github_app_client_id: Client ID of the admins' GitHub App.
        github_app_slug: URL slug of the admins' GitHub App.
        threadvault_owner_id: Slack user ID of the owner of the app, who installed it.
        threadvault_admin_ids: Slack user IDs that may change settings.
        secret_key: Key that encrypts stored secrets,
                    or None to use the key file in the data directory.
        data_directory: Local directory for the data and the vault clone.
        language_display: Language for users whose Slack locale is unknown.
        lookback_days: Number of recent days fetched again on every run.
        deletions_maximum: Most messages one run may delete from the vault,
                           or None for no limit.
    """

    slack_bot_token: str
    slack_app_token: str
    github_app_client_id: str
    github_app_slug: str
    threadvault_owner_id: str
    threadvault_admin_ids: frozenset[str]
    threadvault_secret_key: str | None
    threadvault_data_directory: pathlib.Path
    threadvault_language_display: Language
    threadvault_lookback_days: int
    threadvault_deletions_maximum: int | None

    def require(
        self,
        *fields: FieldRequired
    ) -> None:

        """Checks that settings needed by the caller are present.

        Args:
            *fields: Names of the settings that the caller needs.

        Raises:
            ConfigurationError: One or more of the settings are unset.
                                The message lists every missing environment variable.
        """

        missing = [field.upper() for field in fields if not getattr(self, field)]

        if missing: raise ConfigurationError(f'Missing required environment variables: {', '.join(missing)}')

def load(
    environment: collections.abc.Mapping[str, str] | None = None
) -> Settings:

    """Validates environment variables and builds settings from them.

    Error messages name the offending variable but never repeat its value,
    because the value may be a credential.

    Args:
        environment: Environment variables to build the settings from.
                     When None, the process environment is used, layered over
                     a .env file in the current directory if there is one.

    Returns:
        The validated settings.

    Raises:
        ConfigurationError: A variable has an invalid value.
    """

    if environment is None: environment = _read()

    slack_bot_token = _parse('SLACK_BOT_TOKEN', environment, category = 'environ')
    slack_app_token = _parse('SLACK_APP_TOKEN', environment, category = 'environ')
    github_app_client_id = _parse('GITHUB_APP_CLIENT_ID', environment, category = 'environ')
    github_app_slug = _parse('GITHUB_APP_SLUG', environment, category = 'environ')

    if slack_bot_token and not slack_bot_token.startswith('xoxb-'): raise ConfigurationError('SLACK_BOT_TOKEN must be a bot token starting with xoxb-')
    if slack_app_token and not slack_app_token.startswith('xapp-'): raise ConfigurationError('SLACK_APP_TOKEN must be an app-level token starting with xapp-')
    if github_app_client_id and not _PATTERN_GITHUB_APP_CLIENT_ID.fullmatch(github_app_client_id): raise ConfigurationError('GITHUB_APP_CLIENT_ID may only contain letters, digits and dots')
    if github_app_slug and not _PATTERN_GITHUB_APP_SLUG.fullmatch(github_app_slug): raise ConfigurationError('GITHUB_APP_SLUG may only contain lower-case letters, digits and hyphens')

    return Settings(
        slack_bot_token = slack_bot_token,
        slack_app_token = slack_app_token,
        github_app_client_id = github_app_client_id,
        github_app_slug = github_app_slug,
        threadvault_owner_id = _parse('THREADVAULT_OWNER_ID', environment, category = 'user'),
        threadvault_admin_ids = _parse('THREADVAULT_ADMIN_IDS', environment, category = 'id'),
        threadvault_secret_key = _parse('THREADVAULT_SECRET_KEY', environment, category = 'environ') or None,
        threadvault_data_directory = _parse('THREADVAULT_DATA_DIRECTORY', environment, category = 'directory'),
        threadvault_language_display = _parse('THREADVAULT_LANGUAGE_DISPLAY', environment, category = 'language'),
        threadvault_lookback_days = _parse('THREADVAULT_LOOKBACK_DAYS', environment, category = 'integer', default = LOOKBACK_DAYS_DEFAULT, minimum = 1, maximum = LOOKBACK_DAYS_MAXIMUM),
        threadvault_deletions_maximum = _parse('THREADVAULT_DELETIONS_MAXIMUM', environment, category = 'integer', default = None, minimum = 0)
    )

def _read() -> dict[str, str]:

    values = {key: value for key, value in dotenv.dotenv_values('.env').items() if value is not None}

    return {**values, **os.environ}

@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['environ']) -> str: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['user']) -> str: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['id']) -> frozenset[str]: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['directory']) -> pathlib.Path: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['language']) -> Language: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['integer'], default: int = 0, minimum: int | None = None, maximum: int | None = None) -> int: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['integer'], default: None, minimum: int | None = None, maximum: int | None = None) -> int | None: ...

def _parse(
    name: str,
    environment: collections.abc.Mapping[str, str],
    *,
    category: typing.Literal['environ', 'user', 'id', 'directory', 'language', 'integer'],
    default: int | None = 0,
    minimum: int | None = None,
    maximum: int | None = None
) -> str | frozenset[str] | pathlib.Path | Language | int | None:

    value = environment.get(name, '').strip()

    match category:

        case 'environ':

            return value

        case 'user':

            if value and not _PATTERN_SLACK_USER_ID.fullmatch(value): raise ConfigurationError(f'{name} must be one Slack user ID')

            return value

        case 'id':

            ids = frozenset(part.strip() for part in value.split(',') if part.strip())

            if (invalid := sorted(itertools.filterfalse(_PATTERN_SLACK_USER_ID.fullmatch, ids))): raise ConfigurationError(f'{name} contains invalid Slack user IDs: {', '.join(invalid)}')

            return ids

        case 'directory':

            if not value: return platformdirs.user_data_path(threadvault.product.NAME, appauthor = False)

            return pathlib.Path(value).expanduser().resolve()

        case 'language':

            match value.lower():

                case 'en' | '': return 'en'
                case 'ja': return 'ja'
                case _: raise ConfigurationError(f'{name} must be "en" or "ja"')

        case 'integer':

            if not value: return default

            try: number = int(value)
            except ValueError: raise ConfigurationError(f'{name} must be an integer') from None

            if (minimum is not None and maximum is not None) and not minimum <= number <= maximum: raise ConfigurationError(f'{name} must be between {minimum} and {maximum}')
            if minimum is not None and number < minimum: raise ConfigurationError(f'{name} must be at least {minimum}')
            if maximum is not None and maximum < number: raise ConfigurationError(f'{name} must be at most {maximum}')

            return number
