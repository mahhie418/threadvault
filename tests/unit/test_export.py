import json
import os
import pathlib

import threadvault.vault.export

def locate(
    *names: str
) -> pathlib.Path:

    return pathlib.Path(os.path.join(pathlib.Path(__file__).parents[1], 'fixtures', *names))

def test_export_json_users(
    tmp_path: pathlib.Path
) -> None:

    users = json.loads(locate('slack', 'users.list.json').read_text(encoding = 'utf-8'))
    threadvault.vault.export.users(tmp_path, users)
    file = pathlib.Path(os.path.join(tmp_path, threadvault.vault.export.USERS_FILE))

    assert file.read_bytes() == locate('vault', 'raw', 'users.json').read_bytes()

def test_export_json_channels(
    tmp_path: pathlib.Path
) -> None:

    channels = json.loads(locate('slack', 'conversations.list.json').read_text(encoding = 'utf-8'))
    members = json.loads(locate('slack', 'conversations.members.json').read_text(encoding = 'utf-8'))
    threadvault.vault.export.channels(tmp_path, channels, members)

    for name in (threadvault.vault.export.CHANNELS_FILE, threadvault.vault.export.GROUPS_FILE): assert pathlib.Path(os.path.join(tmp_path, name)).read_bytes() == locate('vault', 'raw', name).read_bytes()
