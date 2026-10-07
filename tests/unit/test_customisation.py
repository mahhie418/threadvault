import collections.abc
import datetime
import os
import pathlib
import typing

import pytest

import threadvault.customisation
import threadvault.storage

SETTINGS_VALID = [
    {'schedule_time': '23:59'},
    {'attachment_size_maximum': 1},
    {'attachment_size_maximum': threadvault.customisation.ATTACHMENT_SIZE_MAXIMUM},
    {'owner_id': 'UXXX1'},
    {'admins_allowed': ('UXXX1', 'WXXX2')},
]

SETTINGS_INVALID = [
    ({'repository_name': 'xxx'}, 'repository_name'),
    ({'repository_name': 'xxx/'}, 'repository_name'),
    ({'schedule_time': '0:00'}, 'schedule_time'),
    ({'schedule_time': '24:00'}, 'schedule_time'),
    ({'workspace_timezone': 'xxx/xxx'}, 'workspace_timezone'),
    ({'channel_mode': 'xxx'}, 'channel_mode'),
    ({'attachment_size_maximum': 0}, 'attachment_size_maximum'),
    ({'attachment_size_maximum': threadvault.customisation.ATTACHMENT_SIZE_MAXIMUM + 1}, 'attachment_size_maximum'),
    ({'markdown_language': 'xxx'}, 'markdown_language'),
    ({'owner_id': 'xxx'}, 'owner_id'),
    ({'admins_allowed': ('UXXX1', 'xxx')}, 'admins_allowed')
]

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

@pytest.fixture
def store(
    database: threadvault.storage.Database
) -> threadvault.customisation.SettingsIO:

    return threadvault.customisation.SettingsIO(database)

@pytest.mark.parametrize('changes', SETTINGS_VALID)
def test_customisation_settings_valid(
    changes: dict[str, typing.Any]
) -> None:

    threadvault.customisation.Settings(**changes)

@pytest.mark.parametrize(('changes', 'field'), SETTINGS_INVALID)
def test_customisation_settings_invalid(
    changes: dict[str, typing.Any],
    field: str
) -> None:

    with pytest.raises(threadvault.customisation.SettingInvalidError) as exception: threadvault.customisation.Settings(**changes)

    assert exception.value.field == field

def test_customisation_settings_store(
    store: threadvault.customisation.SettingsIO
) -> None:

    settings = threadvault.customisation.Settings(
        repository_name = 'xxx/xxx',
        schedule_enabled = False,
        schedule_time = '12:34',
        workspace_timezone = 'Asia/Tokyo',
        channel_mode = 'selected',
        channels_selected = ('xxx1', 'xxx2'),
        channels_joined = False,
        attachments_enabled = False,
        attachment_size_maximum = 50,
        markdown_language = 'ja',
        owner_id = 'UXXX1',
        admins_allowed = ('UXXX1', 'UXXX2'),
    )

    store.save('xxx1', settings, update_user = 'xxx')

    assert store.load('xxx1') == settings
    assert store.load('xxx2') == threadvault.customisation.Settings()

def test_customisation_settings_override(
    store: threadvault.customisation.SettingsIO
) -> None:

    store.save('xxx', threadvault.customisation.Settings(schedule_enabled = False), update_user = 'xxx')
    store.save('xxx', threadvault.customisation.Settings(channels_joined = False), update_user = 'xxx')

    settings = store.load('xxx')

    assert settings.schedule_enabled is True
    assert settings.channels_joined is False

def test_customisation_settings_report(
    database: threadvault.storage.Database,
    store: threadvault.customisation.SettingsIO
) -> None:

    store.save('xxx', threadvault.customisation.Settings(), update_user = 'xxx')

    cursor = database.connect().execute('SELECT update_user, update_time FROM slack')
    update_user, update_time = cursor.fetchone()

    assert update_user == 'xxx'
    assert datetime.datetime.fromisoformat(update_time).tzinfo is not None

def test_customisation_workspace_unknown(
    store: threadvault.customisation.SettingsIO
) -> None:

    assert store.load('xxx') == threadvault.customisation.Settings()

def test_customisation_json_unknown() -> None:

    text = '{"workspace_timezone": "Asia/Tokyo", "xxx": 1}'
    settings = threadvault.customisation.Settings.decode(text)

    assert settings == threadvault.customisation.Settings(workspace_timezone = 'Asia/Tokyo')

def test_customisation_json_conversion() -> None:

    settings = threadvault.customisation.Settings(channel_mode = 'selected', channels_selected = ('xxx2', 'xxx1'), admins_allowed = ('UXXX2', 'UXXX1'))

    assert settings == threadvault.customisation.Settings.decode(settings.encode())
