# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import json
import os
import pathlib

import pytest

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

def test_export_json_messages(
    tmp_path: pathlib.Path
) -> None:

    messages = json.loads(locate('slack', 'messages.json').read_text(encoding = 'utf-8'))
    users = json.loads(locate('slack', 'users.list.json').read_text(encoding = 'utf-8'))
    directory = pathlib.Path(os.path.join(tmp_path, 'general'))
    threadvault.vault.export.messages(directory, messages, users)
    names = sorted(entry.name for entry in directory.iterdir())

    assert names == sorted(entry.name for entry in locate('vault', 'raw', 'general').iterdir())
    for name in names: assert pathlib.Path(os.path.join(directory, name)).read_bytes() == locate('vault', 'raw', 'general', name).read_bytes()

def test_export_json_deletion(
    tmp_path: pathlib.Path
) -> None:

    messages = json.loads(locate('slack', 'messages.json').read_text(encoding = 'utf-8'))
    users = json.loads(locate('slack', 'users.list.json').read_text(encoding = 'utf-8'))
    threadvault.vault.export.messages(tmp_path, messages, users)
    threadvault.vault.export.messages(tmp_path, [message for message in messages if message['ts'] in {'1510880400.000000', '1510963199.000000'}], users)

    assert [entry.name for entry in tmp_path.iterdir()] == ['2017-11-17.json']

def test_export_json_interruption(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    file = pathlib.Path(os.path.join(tmp_path, threadvault.vault.export.USERS_FILE))
    threadvault.vault.export.users(tmp_path, [])
    previous = file.read_bytes()
    write = pathlib.Path.write_text

    def interrupt(
        path: pathlib.Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None
    ) -> int:

        write(path, data[:1], encoding = encoding, errors = errors, newline = newline)

        raise OSError('xxx')

    monkeypatch.setattr(pathlib.Path, 'write_text', interrupt)

    with pytest.raises(OSError, match = 'xxx'): threadvault.vault.export.users(tmp_path, [])

    assert file.read_bytes() == previous
    assert [entry.name for entry in tmp_path.iterdir()] == [threadvault.vault.export.USERS_FILE]
