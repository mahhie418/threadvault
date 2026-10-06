"""Workspace settings that admins change from the App Home."""

import dataclasses
import datetime
import json
import re
import typing
import zoneinfo

import threadvault.configuration
import threadvault.storage

ATTACHMENT_SIZE_MAXIMUM = 100

type ChannelMode = typing.Literal['joined', 'selected']

_SETTINGS_SELECT = 'SELECT configuration_data FROM slack WHERE workspace_id = ?'

_SETTINGS_UPSERT = """
    INSERT INTO slack (workspace_id, configuration_data, update_user, update_time)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (workspace_id) DO UPDATE SET
        configuration_data = excluded.configuration_data,
        update_user = excluded.update_user,
        update_time = excluded.update_time
"""

class SettingInvalidError(ValueError):

    """Raised when a setting has an invalid value.

    Attributes:
        field: Name of the setting with the invalid value.
    """

    def __init__(
        self,
        field: str,
        message: str
    ) -> None:

        """Initialises the error.

        Args:
            field: Name of the setting with the invalid value.
            message: Explanation for the admin.
        """

        super().__init__(message)

        self.field = field

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Settings:

    """Settings for one workspace. Instances are always valid.

    Attributes:
        repository_name: Destination repository as owner/name,
                         or None before an admin chooses one.
        schedule_enabled: Whether the daily backup runs.
        schedule_time: Time of the daily backup as HH:MM.
        workspace_timezone: IANA time zone for the schedule and the Markdown files.
        channel_mode: Back up every channel the bot is in ('joined')
                      or only `channels_selected` ('selected').
        channels_selected: Channels to back up in 'selected' mode.
        channels_joined: Whether the bot joins every public channel.
        attachments_enabled: Whether attachments are saved.
        attachment_size_maximum: Largest attachment to save, in MiB.
        markdown_language: Language of the headings in the Markdown files.
        admins_allowed: Admins whom the owner allows to operate the app.
    """

    repository_name: str | None = None
    schedule_enabled: bool = True
    schedule_time: str = '00:00'
    workspace_timezone: str = 'UTC'
    channel_mode: ChannelMode = 'joined'
    channels_selected: tuple[str, ...] = ()
    channels_joined: bool = True
    attachments_enabled: bool = True
    attachment_size_maximum: int = 20
    markdown_language: threadvault.configuration.Language = 'en'
    admins_allowed: tuple[str, ...] = ()

    _PATTERN_REPOSITORY = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+')
    _PATTERN_TIME = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d')
    _PATTERN_USER = re.compile(r'[UW][A-Z0-9]{2,}')

    def __post_init__(
        self
    ) -> None:

        """Validates the settings.

        Raises:
            SettingInvalidError: A setting has an invalid value.
        """

        if self.repository_name is not None and not self._PATTERN_REPOSITORY.fullmatch(self.repository_name): raise SettingInvalidError('repository_name', 'Repository must look like owner/name')
        if not self._PATTERN_TIME.fullmatch(self.schedule_time): raise SettingInvalidError('schedule_time', 'Time must be HH:MM on a 24-hour clock')

        try: zoneinfo.ZoneInfo(self.workspace_timezone)
        except zoneinfo.ZoneInfoNotFoundError, ValueError: raise SettingInvalidError('workspace_timezone', f'Unknown time zone: {self.workspace_timezone}') from None

        if self.channel_mode not in {'joined', 'selected'}: raise SettingInvalidError('channel_mode', 'Channel mode must be joined or selected')
        if not 1 <= self.attachment_size_maximum <= ATTACHMENT_SIZE_MAXIMUM: raise SettingInvalidError('attachment_size_maximum', f'Attachment limit must be between 1 and {ATTACHMENT_SIZE_MAXIMUM} MiB')
        if self.markdown_language not in {'en', 'ja'}: raise SettingInvalidError('markdown_language', 'Markdown language must be en or ja')
        if not all(map(self._PATTERN_USER.fullmatch, self.admins_allowed)): raise SettingInvalidError('admins_allowed', 'Admins must be Slack user IDs')

    def encode(
        self
    ) -> str:

        """Returns the settings as a JSON document with sorted keys."""

        return json.dumps(dataclasses.asdict(self), ensure_ascii = False, sort_keys = True)

    @classmethod
    def decode(
        cls,
        text: str
    ) -> typing.Self:

        """Rebuilds settings from a JSON document made by `encode`.

        Keys that no longer exist are ignored, and settings added since the
        document was written take their default values.

        Args:
            text: The JSON document.

        Returns:
            The settings.

        Raises:
            SettingInvalidError: The document holds an invalid value.
        """

        data: dict[str, typing.Any] = json.loads(text)
        names = {field.name for field in dataclasses.fields(cls)}
        values = {key: value for key, value in data.items() if key in names}

        if 'channels_selected' in values: values['channels_selected'] = tuple(values['channels_selected'])
        if 'admins_allowed' in values: values['admins_allowed'] = tuple(values['admins_allowed'])

        return cls(**values)

class SettingsIO:

    """Reads and writes workspace settings in the database."""

    def __init__(
        self,
        database: threadvault.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the settings.
        """

        self._database = database

    def load(
        self,
        workspace_id: str
    ) -> Settings:

        """Loads the settings of a workspace.

        Args:
            workspace_id: Slack workspace ID.

        Returns:
            The saved settings, or the defaults when none have been saved.
        """

        row = self._database.connect().execute(_SETTINGS_SELECT, (workspace_id,)).fetchone()

        if row is None: return Settings()

        return Settings.decode(row['configuration_data'])

    def save(
        self,
        workspace_id: str,
        settings: Settings,
        *,
        update_user: str
    ) -> None:

        """Saves the settings of a workspace, replacing any earlier ones.

        Args:
            workspace_id: Slack workspace ID.
            settings: The settings to save.
            update_user: Slack user ID of the admin who made the change.
        """

        update_time = datetime.datetime.now(datetime.UTC).isoformat()

        with self._database.begin() as connection: connection.execute(_SETTINGS_UPSERT, (workspace_id, settings.encode(), update_user, update_time))
