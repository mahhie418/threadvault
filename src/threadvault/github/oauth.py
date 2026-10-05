"""GitHub OAuth through the device flow, which connects a GitHub account without a client secret."""

import collections.abc
import dataclasses
import datetime
import time
import typing

import httpx

CODE_URL = 'https://github.com/login/device/code'
ACCESS_URL = 'https://github.com/login/oauth/access_token'

TIMEOUT_LIMIT = 30.
INTERVAL_INCREMENT = 5

class OAuthError(Exception):

    """Raised when GitHub gives no tokens, in the device flow or a refresh.

    Attributes:
        reason: Error code from GitHub, such as expired_token or access_denied,
                or connection when GitHub could not be reached.
    """

    def __init__(
        self,
        reason: str,
        message: str
    ) -> None:

        """Initialises the error.

        Args:
            reason: Error code from GitHub, or connection.
            message: Explanation for the admin.
        """

        super().__init__(message)

        self.reason = reason

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Code:

    """Code that the user enters on GitHub to connect the account.

    Attributes:
        device_code: Code that identifies the request while polling.
        user_code: Code for the user to enter.
        verification_uri: Page where the user enters the code.
        interval: Seconds to wait between polls.
    """

    device_code: str
    user_code: str
    verification_uri: str
    interval: int

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Tokens:

    """Tokens with which the GitHub App acts for the user.

    Attributes:
        access_token: Token for the API and git (ghu_...).
        access_expiry: When the access token expires.
        refresh_token: Token that gets a new pair once (ghr_...).
        refresh_expiry: When the refresh token expires.
    """

    access_token: str
    access_expiry: datetime.datetime
    refresh_token: str
    refresh_expiry: datetime.datetime

def request(
    client_id: str
) -> Code:

    """Asks GitHub for a code for the user to enter.

    Args:
        client_id: Client ID of the GitHub App.

    Returns:
        The code.

    Raises:
        OAuthError: GitHub refused, or could not be reached.
    """

    data = _post(CODE_URL, {'client_id': client_id})

    if 'error' in data: raise OAuthError(data['error'], data.get('error_description') or data['error'])

    return Code(device_code = data['device_code'], user_code = data['user_code'], verification_uri = data['verification_uri'], interval = data['interval'])

def poll(
    client_id: str,
    code: Code,
    *,
    sleep: collections.abc.Callable[[float], None] = time.sleep
) -> Tokens:

    """Waits until the user has entered the code, and gets the tokens.

    While the user has not decided yet, GitHub is asked again after the
    interval of the code; when it asks to slow down, the interval grows.

    Args:
        client_id: Client ID of the GitHub App.
        code: Code from `request`.
        sleep: Function that waits for a number of seconds.

    Returns:
        The tokens.

    Raises:
        OAuthError: The code expired, the user refused, GitHub refused
                    for another reason, or GitHub could not be reached.
    """

    interval = code.interval

    while True:

        sleep(interval)

        data = _post(ACCESS_URL, {'client_id': client_id, 'device_code': code.device_code, 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})

        match data.get('error'):

            case None: return _issue(data)
            case 'authorization_pending': continue
            case 'slow_down': interval = data.get('interval', interval + INTERVAL_INCREMENT)
            case reason: raise OAuthError(reason, data.get('error_description') or reason)

def refresh(
    client_id: str,
    refresh_token: str
) -> Tokens:

    """Gets a new pair of tokens with a refresh token, which works only once.

    Args:
        client_id: Client ID of the GitHub App.
        refresh_token: Refresh token from earlier tokens.

    Returns:
        The new tokens.

    Raises:
        OAuthError: GitHub refused the refresh token, or could not be reached.
    """

    data = _post(ACCESS_URL, {'client_id': client_id, 'grant_type': 'refresh_token', 'refresh_token': refresh_token})

    if 'error' in data: raise OAuthError(data['error'], data.get('error_description') or data['error'])

    return _issue(data)

def _post(
    url: str,
    form: dict[str, str]
) -> dict[str, typing.Any]:

    try: response = httpx.post(url, data = form, headers = {'Accept': 'application/json'}, timeout = TIMEOUT_LIMIT).raise_for_status()
    except httpx.HTTPError as error: raise OAuthError('connection', f'GitHub could not be reached: {error}') from error

    return response.json()

def _issue(
    data: dict[str, typing.Any]
) -> Tokens:

    if 'refresh_token' not in data: raise OAuthError('expiry', 'The GitHub App must let user tokens expire, so that they can be refreshed')

    issue = datetime.datetime.now(datetime.UTC)

    return Tokens(access_token = data['access_token'], access_expiry = issue + datetime.timedelta(seconds = data['expires_in']), refresh_token = data['refresh_token'], refresh_expiry = issue + datetime.timedelta(seconds = data['refresh_token_expires_in']))
