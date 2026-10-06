"""GitHub REST API calls that find and create the repository of the vault."""

import http
import typing

import httpx

API_URL = 'https://api.github.com'
API_VERSION = '2022-11-28'

TIMEOUT_LIMIT = 30.

class GitHubError(Exception):

    """Raised when GitHub refuses a request or cannot be reached.

    Attributes:
        status: HTTP status of the answer, or 0 when GitHub could not be reached.
    """

    def __init__(
        self,
        status: int,
        message: str
    ) -> None:

        """Initialises the error.

        Args:
            status: HTTP status of the answer, or 0.
            message: Explanation for the admin.
        """

        super().__init__(message)

        self.status = status

def user(
    token: str
) -> dict[str, typing.Any]:

    """Fetches the GitHub user of a token.

    Args:
        token: Access token of the user.

    Returns:
        The user, as GET /user returns it.

    Raises:
        GitHubError: GitHub refused the request, or could not be reached.
    """

    return _request('GET', '/user', token).json()

def repository(
    token: str,
    full_name: str
) -> dict[str, typing.Any] | None:

    """Fetches a repository.

    Args:
        token: Access token of the user.
        full_name: Owner and name of the repository, as owner/name.

    Returns:
        The repository, as GET /repos/{owner}/{name} returns it, or None
        when it does not exist or the token cannot see it.

    Raises:
        GitHubError: GitHub refused the request for another reason, or could not be reached.
    """

    try:

        return _request('GET', f'/repos/{full_name}', token).json()

    except GitHubError as error:

        if error.status == http.HTTPStatus.NOT_FOUND: return None

        raise

def create(
    token: str,
    full_name: str
) -> dict[str, typing.Any]:

    """Creates a private repository with a first commit.

    The repository belongs to the user of the token when the owner is that
    user, and to the organisation of that name otherwise.

    Args:
        token: Access token of the user.
        full_name: Owner and name of the repository, as owner/name.

    Returns:
        The repository, as GitHub returns it after creating it.

    Raises:
        GitHubError: GitHub refused the request, or could not be reached.
    """

    owner, _, name = full_name.partition('/')
    login: str = user(token)['login']
    path = '/user/repos' if owner.casefold() == login.casefold() else f'/orgs/{owner}/repos'

    return _request('POST', path, token, body = {'name': name, 'private': True, 'auto_init': True}).json()

def _request(
    method: str,
    path: str,
    token: str,
    body: dict[str, typing.Any] | None = None
) -> httpx.Response:

    headers = {'Accept': 'application/vnd.github+json', 'Authorization': f'Bearer {token}', 'X-GitHub-Api-Version': API_VERSION}

    try: response = httpx.request(method, f'{API_URL}{path}', headers = headers, json = body, timeout = TIMEOUT_LIMIT)
    except httpx.HTTPError as error: raise GitHubError(0, f'GitHub could not be reached: {error}') from error

    if response.is_error: raise GitHubError(response.status_code, f'GitHub answered {response.status_code} to {method} {path}: {response.text}')

    return response
