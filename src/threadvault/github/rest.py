"""GitHub REST API calls that find and create the repository of the vault."""

import http
import typing

import httpx

API_URL = 'https://api.github.com'
API_VERSION = '2022-11-28'

PAGE_SIZE = 100
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

class RepositoryCache:

    """Names of the private repositories that the connected account can back up into, kept for filtering.

    Slack waits only 3 seconds for the options of a menu, which may be too
    short for GitHub to list every repository, so the names are fetched
    beforehand and then filtered as the admin types.
    """

    def __init__(
        self
    ) -> None:

        """Initialises the cache, which holds nothing until the first update."""

        self._names: list[str] | None = None

    def update(
        self,
        token: str
    ) -> None:

        """Fetches the names again, from every installation of the GitHub App that the user can access.

        Args:
            token: Access token of the user.

        Raises:
            GitHubError: GitHub refused a request, or could not be reached.
        """

        names = {repository['full_name'] for installation in installations(token) for repository in repositories(token, installation['id']) if repository['private']}

        self._names = sorted(names, key = str.casefold)

    def search(
        self,
        query: str
    ) -> list[str] | None:

        """Gives the names that contain a text, ignoring case.

        Args:
            query: The text, which may be empty.

        Returns:
            The names in alphabetical order, or None before the first update.
        """

        if self._names is None: return None

        return [name for name in self._names if query.casefold() in name.casefold()]

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

def installations(
    token: str
) -> list[dict[str, typing.Any]]:

    """Fetches the installations of the GitHub App that the user can access.

    Args:
        token: Access token of the user.

    Returns:
        The installations, as GET /user/installations lists them, up to 100,
        more than one GitHub App of a deployment is ever installed on.

    Raises:
        GitHubError: GitHub refused the request, or could not be reached.
    """

    return _request('GET', f'/user/installations?per_page={PAGE_SIZE}', token).json()['installations']

def repositories(
    token: str,
    installation: int
) -> list[dict[str, typing.Any]]:

    """Fetches every repository of an installation of the GitHub App that the user can access.

    Args:
        token: Access token of the user.
        installation: ID of the installation.

    Returns:
        The repositories, as GET /user/installations/{id}/repositories lists them.

    Raises:
        GitHubError: GitHub refused a request, or could not be reached.
    """

    entries = []
    page = 1

    while True:

        data = _request('GET', f'/user/installations/{installation}/repositories?per_page={PAGE_SIZE}&page={page}', token).json()
        entries.extend(data['repositories'])

        if not data['repositories'] or len(entries) >= data['total_count']: return entries

        page += 1

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
