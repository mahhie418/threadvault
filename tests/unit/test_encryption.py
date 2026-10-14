# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import os
import pathlib
import stat
import sys

import cryptography.fernet
import pytest

import threadvault.encryption

TEXT = 'xxx-テスト'

def create() -> threadvault.encryption.SecretCipher:

    return threadvault.encryption.SecretCipher(threadvault.encryption.generate().encode('ascii'))

def test_encryption_key_entry() -> None:

    cryptography.fernet.Fernet(threadvault.encryption.generate())

def test_encryption_key_conversion() -> None:

    cipher = create()
    text = cipher.encrypt(TEXT)

    assert TEXT not in text
    assert cipher.decrypt(text) == TEXT

def test_encryption_key_consistency() -> None:

    ciphers = [create() for _ in range(2)]
    text = ciphers[0].encrypt(TEXT)

    with pytest.raises(threadvault.encryption.SecretKeyError, match = 'cannot be decrypted'): ciphers[1].decrypt(text)

def test_encryption_key_robustness() -> None:

    cipher = create()
    text = cipher.encrypt(TEXT)

    replacement = 'A' if text[20] != 'A' else 'B'
    fake = text[:20] + replacement + text[21:]

    with pytest.raises(threadvault.encryption.SecretKeyError): cipher.decrypt(fake)

def test_encryption_key_selection(
    tmp_path: pathlib.Path
) -> None:

    key = threadvault.encryption.generate()
    file = pathlib.Path(os.path.join(tmp_path, threadvault.encryption.KEY_FILE))

    assert threadvault.encryption.load(key, tmp_path) == key.encode('ascii')
    assert not file.exists()

def test_encryption_key_invalid(
    tmp_path: pathlib.Path
) -> None:

    with pytest.raises(threadvault.encryption.SecretKeyError, match = 'THREADVAULT_SECRET_KEY') as exception: threadvault.encryption.load('xxx', tmp_path)

    assert 'xxx' not in str(exception.value)

def test_encryption_key_creation(
    tmp_path: pathlib.Path
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'xxx', 'xxx'))
    file = pathlib.Path(os.path.join(directory, threadvault.encryption.KEY_FILE))

    keys = [threadvault.encryption.load(None, directory) for _ in range(2)]

    assert keys[0] == keys[1]
    assert file.is_file()

    cryptography.fernet.Fernet(keys[0])

@pytest.mark.skipif(sys.platform == 'win32', reason = 'POSIX permissions only')
def test_encryption_key_permission(
    tmp_path: pathlib.Path
) -> None:

    directory = pathlib.Path(os.path.join(tmp_path, 'xxx'))
    file = pathlib.Path(os.path.join(directory, threadvault.encryption.KEY_FILE))

    threadvault.encryption.load(None, directory)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(file.stat().st_mode) == 0o600

def test_encryption_key_corruption(
    tmp_path: pathlib.Path
) -> None:

    file = pathlib.Path(os.path.join(tmp_path, threadvault.encryption.KEY_FILE))
    file.write_text('xxx\n', encoding = 'ascii')

    with pytest.raises(threadvault.encryption.SecretKeyError, match = threadvault.encryption.KEY_FILE): threadvault.encryption.load(None, tmp_path)
