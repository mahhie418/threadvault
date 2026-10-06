import datetime
import typing
import urllib.parse

import httpx
import pytest
import respx

import threadvault.github.oauth

CODE = threadvault.github.oauth.Code(device_code = 'xxx1', user_code = 'XXXX-XXXX', verification_uri = 'https://github.com/login/device', interval = 5)
TOKENS = {'access_token': 'ghu_xxx', 'expires_in': 28800, 'refresh_token': 'ghr_xxx', 'refresh_token_expires_in': 15897600, 'scope': '', 'token_type': 'bearer'}

REQUESTS_FAILED = [
    (httpx.ConnectError('xxx'), 'connection'),
    (httpx.Response(200, json = {'error': 'device_flow_disabled', 'error_description': 'xxx'}), 'device_flow_disabled')
]

POLLS_FAILED = [
    ({'error': 'expired_token', 'error_description': 'xxx'}, 'expired_token'),
    ({'error': 'access_denied', 'error_description': 'xxx'}, 'access_denied'),
    ({'access_token': 'ghu_xxx', 'scope': '', 'token_type': 'bearer'}, 'expiry')
]

def read(
    request: httpx.Request
) -> dict[str, list[str]]:

    return urllib.parse.parse_qs(request.content.decode('ascii'))

def test_oauth_code_success() -> None:

    with respx.mock:

        route = respx.post(threadvault.github.oauth.CODE_URL).respond(200, json = {'device_code': 'xxx1', 'expires_in': 900, 'interval': 5, 'user_code': 'XXXX-XXXX', 'verification_uri': 'https://github.com/login/device'})
        code = threadvault.github.oauth.request('xxx')

    assert code == CODE
    assert read(route.calls.last.request) == {'client_id': ['xxx']}

@pytest.mark.parametrize(('effect', 'reason'), REQUESTS_FAILED)
def test_oauth_code_failure(
    effect: httpx.ConnectError | httpx.Response,
    reason: str
) -> None:

    with respx.mock:

        respx.post(threadvault.github.oauth.CODE_URL).mock(side_effect = [effect])

        with pytest.raises(threadvault.github.oauth.OAuthError) as exception: threadvault.github.oauth.request('xxx')

    assert exception.value.reason == reason

def test_oauth_token_success() -> None:

    sleeps = []
    responses = [httpx.Response(200, json = {'error': 'authorization_pending'}), httpx.Response(200, json = {'error': 'slow_down', 'interval': 15}), httpx.Response(200, json = {'error': 'slow_down'}), httpx.Response(200, json = TOKENS)]

    with respx.mock:

        route = respx.post(threadvault.github.oauth.ACCESS_URL).mock(side_effect = responses)
        issue = datetime.datetime.now(datetime.UTC)
        tokens = threadvault.github.oauth.poll('xxx', CODE, sleep = sleeps.append)

    assert sleeps == [5, 5, 15, 20]
    assert read(route.calls.last.request) == {'client_id': ['xxx'], 'device_code': ['xxx1'], 'grant_type': ['urn:ietf:params:oauth:grant-type:device_code']}
    assert (tokens.access_token, tokens.refresh_token) == ('ghu_xxx', 'ghr_xxx')
    assert datetime.timedelta(seconds = 28800) <= tokens.access_expiry - issue < datetime.timedelta(seconds = 28860)
    assert datetime.timedelta(seconds = 15897600) <= tokens.refresh_expiry - issue < datetime.timedelta(seconds = 15897660)

@pytest.mark.parametrize(('data', 'reason'), POLLS_FAILED)
def test_oauth_token_failure(
    data: dict[str, typing.Any],
    reason: str
) -> None:

    sleeps = []

    with respx.mock:

        respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = data)

        with pytest.raises(threadvault.github.oauth.OAuthError) as exception: threadvault.github.oauth.poll('xxx', CODE, sleep = sleeps.append)

    assert exception.value.reason == reason

def test_oauth_token_refresh() -> None:

    with respx.mock:

        route = respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = TOKENS)
        tokens = threadvault.github.oauth.refresh('xxx', 'ghr_xxx1')

    assert read(route.calls.last.request) == {'client_id': ['xxx'], 'grant_type': ['refresh_token'], 'refresh_token': ['ghr_xxx1']}
    assert (tokens.access_token, tokens.refresh_token) == ('ghu_xxx', 'ghr_xxx')

def test_oauth_token_stall() -> None:

    with respx.mock:

        respx.post(threadvault.github.oauth.ACCESS_URL).respond(200, json = {'error': 'bad_refresh_token', 'error_description': 'xxx'})

        with pytest.raises(threadvault.github.oauth.OAuthError) as exception: threadvault.github.oauth.refresh('xxx', 'ghr_xxx1')

    assert exception.value.reason == 'bad_refresh_token'
