import json
import typing

import httpx
import pytest
import respx

import threadvault.github.rest

REPOSITORIES_FOUND = [
    (200, {'full_name': 'xxx/xxx', 'private': True}, {'full_name': 'xxx/xxx', 'private': True}),
    (404, {'message': 'Not Found'}, None)
]

REPOSITORIES_CREATED = [('xxx/xxx1', '/user/repos'), ('XXX/xxx1', '/user/repos'), ('xxx2/xxx1', '/orgs/xxx2/repos')]

REQUESTS_FAILED = [
    (httpx.ConnectError('xxx'), 0),
    (httpx.Response(401, json = {'message': 'Bad credentials'}), 401)
]

def test_rest_user_success() -> None:

    with respx.mock:

        route = respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
        user = threadvault.github.rest.user('ghu_xxx')

    headers = route.calls.last.request.headers

    assert user == {'login': 'xxx'}
    assert (headers['authorization'], headers['accept'], headers['x-github-api-version']) == ('Bearer ghu_xxx', 'application/vnd.github+json', '2022-11-28')

@pytest.mark.parametrize(('effect', 'status'), REQUESTS_FAILED)
def test_rest_user_failure(
    effect: httpx.ConnectError | httpx.Response,
    status: int
) -> None:

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user').mock(side_effect = [effect])

        with pytest.raises(threadvault.github.rest.GitHubError) as exception: threadvault.github.rest.user('ghu_xxx')

    assert exception.value.status == status

def test_rest_installation_list() -> None:

    with respx.mock:

        route = respx.get(f'{threadvault.github.rest.API_URL}/user/installations').respond(200, json = {'total_count': 1, 'installations': [{'id': 1}]})
        installations = threadvault.github.rest.installations('ghu_xxx')

    assert installations == [{'id': 1}]
    assert route.calls.last.request.url.params['per_page'] == '100'

@pytest.mark.parametrize(('full_name', 'path'), REPOSITORIES_CREATED)
def test_rest_repository_creation(
    full_name: str,
    path: str
) -> None:

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/user').respond(200, json = {'login': 'xxx'})
        route = respx.post(f'{threadvault.github.rest.API_URL}{path}').respond(201, json = {'full_name': full_name})
        threadvault.github.rest.create('ghu_xxx', full_name)

    assert json.loads(route.calls.last.request.content) == {'name': 'xxx1', 'private': True, 'auto_init': True}

@pytest.mark.parametrize(('status', 'body', 'expected'), REPOSITORIES_FOUND)
def test_rest_repository_lookup(
    status: int,
    body: dict[str, typing.Any],
    expected: dict[str, typing.Any] | None
) -> None:

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').respond(status, json = body)
        repository = threadvault.github.rest.repository('ghu_xxx', 'xxx/xxx')

    assert repository == expected

def test_rest_repository_failure() -> None:

    with respx.mock:

        respx.get(f'{threadvault.github.rest.API_URL}/repos/xxx/xxx').respond(401, json = {'message': 'Bad credentials'})

        with pytest.raises(threadvault.github.rest.GitHubError) as exception: threadvault.github.rest.repository('ghu_xxx', 'xxx/xxx')

    assert exception.value.status == 401
