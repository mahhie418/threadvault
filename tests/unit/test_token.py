import collections.abc
import datetime
import os
import pathlib
import threading
import time

import httpx
import pytest
import respx

import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.token
import threadvault.storage

NOW = datetime.datetime(2026, 10, 5, 0, 0, tzinfo = datetime.UTC)

TOKENS_SAVED = threadvault.github.oauth.Tokens(access_token = 'ghu_xxx1', access_expiry = NOW + datetime.timedelta(hours = 8), refresh_token = 'ghr_xxx1', refresh_expiry = NOW + datetime.timedelta(days = 184))
TOKENS_REFRESHED = {'access_token': 'ghu_xxx2', 'expires_in': 28800, 'refresh_token': 'ghr_xxx2', 'refresh_token_expires_in': 15897600, 'scope': '', 'token_type': 'bearer'}

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[threadvault.storage.Database]:

    opening = threadvault.storage.Database(pathlib.Path(os.path.join(tmp_path, threadvault.storage.DATABASE_FILE))); yield opening
    opening.close()

@pytest.fixture
def manager(
    database: threadvault.storage.Database
) -> threadvault.github.token.TokenManager:

    cipher = threadvault.encryption.SecretCipher(threadvault.encryption.generate().encode('ascii'))

    return threadvault.github.token.TokenManager(database, cipher, 'xxx')

def respond(
    _: httpx.Request
) -> httpx.Response:

    time.sleep(0.1)

    return httpx.Response(200, json = TOKENS_REFRESHED)

def test_token_pair_encryption(
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock: token = manager.acquire(NOW)

    stored: str = database.connect().execute('SELECT credential_data FROM github').fetchone()[0]

    assert token == 'ghu_xxx1'
    assert 'ghu_xxx1' not in stored
    assert 'ghr_xxx1' not in stored

def test_token_pair_refresh(
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    boundary = TOKENS_SAVED.access_expiry - datetime.timedelta(minutes = 5)

    with respx.mock:

        route = respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = TOKENS_REFRESHED)
        tokens = [manager.acquire(boundary - datetime.timedelta(seconds = 1)), manager.acquire(boundary), manager.acquire(boundary)]

    assert tokens == ['ghu_xxx1', 'ghu_xxx2', 'ghu_xxx2']
    assert route.call_count == 1

def test_token_pair_concurrency(
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    tokens = []
    threads = [threading.Thread(target = lambda: tokens.append(manager.acquire(TOKENS_SAVED.access_expiry))) for _ in range(2)]

    with respx.mock:

        route = respx.post(threadvault.github.oauth.ACCESS_URL).mock(side_effect = respond)

        for thread in threads: thread.start()
        for thread in threads: thread.join()

    assert tokens == ['ghu_xxx2', 'ghu_xxx2']
    assert route.call_count == 1

def test_token_pair_missing(
    manager: threadvault.github.token.TokenManager
) -> None:

    with pytest.raises(threadvault.github.token.TokenError, match = 'not connected'): manager.acquire(NOW)

def test_token_pair_expiry(
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock, pytest.raises(threadvault.github.token.TokenError, match = 'expired'): manager.acquire(TOKENS_SAVED.refresh_expiry)

def test_token_pair_stall(
    manager: threadvault.github.token.TokenManager
) -> None:

    manager.save(TOKENS_SAVED)

    with respx.mock:

        respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = {'error': 'bad_refresh_token', 'error_description': 'xxx'})

        with pytest.raises(threadvault.github.token.TokenError, match = 'could not be refreshed'): manager.acquire(TOKENS_SAVED.access_expiry)
