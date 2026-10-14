# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import base64
import collections.abc
import os
import pathlib
import subprocess
import unittest.mock

import pytest

import threadvault.vault.repository
import threadvault.vault.state

SOURCES_IGNORED = ['vault', 'global']

def create(
    remote: pathlib.Path,
    path: pathlib.Path,
    token: str | None = None
) -> threadvault.vault.repository.Repository:

    repository = threadvault.vault.repository.Repository(path, token = None if token is None else lambda: token, name = 'xxx1', email = 'xxx1@xxx.xxx')
    repository.clone(str(remote))

    return repository

def write(
    repository: threadvault.vault.repository.Repository,
    name: str,
    text: str = 'xxx'
) -> None:

    pathlib.Path(os.path.join(repository.path, name)).write_text(text, encoding = 'utf-8')

def test_repository_version_check(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    git: collections.abc.Callable[..., str]
) -> None:

    assert threadvault.vault.repository.verify() == git('--version', directory = tmp_path).strip().removeprefix('git version ')

    monkeypatch.setattr(threadvault.vault.repository, 'VERSION_MINIMUM', (999, 0))

    with pytest.raises(threadvault.vault.repository.GitError, match = 'or newer is needed'): threadvault.vault.repository.verify()

def test_repository_tree_refresh(
    tmp_path: pathlib.Path,
    remote: pathlib.Path
) -> None:

    repository = create(remote, pathlib.Path(os.path.join(tmp_path, 'clone')))
    write(repository, 'README.md', 'xxx2')
    write(repository, 'xxx.txt')
    repository.refresh()

    assert sorted(entry.name for entry in repository.path.iterdir()) == ['.git', 'README.md']
    assert pathlib.Path(os.path.join(repository.path, 'README.md')).read_text(encoding = 'utf-8') == '# xxx'

def test_repository_push_commit(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    git: collections.abc.Callable[..., str]
) -> None:

    repository = create(remote, pathlib.Path(os.path.join(tmp_path, 'clone')))

    assert not repository.commit('xxx2')

    write(repository, 'xxx.txt')

    assert repository.commit('xxx2')

    repository.push()

    assert git('log', '--format=%s %an', 'main', directory = remote).splitlines() == ['xxx2 xxx1', 'xxx xxx']
    assert repository.head() == git('rev-parse', 'main', directory = remote).strip()

def test_repository_push_rebase(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    git: collections.abc.Callable[..., str]
) -> None:

    first = create(remote, pathlib.Path(os.path.join(tmp_path, 'first')))
    second = create(remote, pathlib.Path(os.path.join(tmp_path, 'second')))

    write(first, 'xxx1.txt')
    first.commit('xxx1')
    first.push()

    write(second, 'xxx2.txt')
    second.commit('xxx2')
    second.push()

    assert git('log', '--format=%s', 'main', directory = remote).splitlines() == ['xxx2', 'xxx1', 'xxx']

def test_repository_push_conflict(
    tmp_path: pathlib.Path,
    remote: pathlib.Path,
    git: collections.abc.Callable[..., str]
) -> None:

    first = create(remote, pathlib.Path(os.path.join(tmp_path, 'first')))
    second = create(remote, pathlib.Path(os.path.join(tmp_path, 'second')))

    write(first, 'README.md', 'xxx1')
    first.commit('xxx1')
    first.push()

    write(second, 'README.md', 'xxx2')
    second.commit('xxx2')
    with pytest.raises(threadvault.vault.repository.GitError, match = 'rebase'): second.push()

    assert not pathlib.Path(os.path.join(second.path, '.git', 'rebase-merge')).exists()
    assert git('log', '--format=%s', 'main', directory = remote).splitlines() == ['xxx1', 'xxx']

def test_repository_hook_isolation(
    tmp_path: pathlib.Path,
    remote: pathlib.Path
) -> None:

    repository = create(remote, pathlib.Path(os.path.join(tmp_path, 'clone')))
    hook = pathlib.Path(os.path.join(repository.path, '.git', 'hooks', 'pre-commit'))
    hook.write_text('#!/bin/sh\nexit 1\n', encoding = 'utf-8')
    hook.chmod(0o755)
    write(repository, 'xxx.txt')

    assert repository.commit('xxx2')

def test_repository_token_isolation(
    tmp_path: pathlib.Path,
    remote: pathlib.Path
) -> None:

    header = f'Authorization: Basic {base64.b64encode(b'x-access-token:ghu_xxx').decode('ascii')}'

    with unittest.mock.patch.object(subprocess, 'run', wraps = subprocess.run) as run:

        repository = create(remote, pathlib.Path(os.path.join(tmp_path, 'clone')), 'ghu_xxx')
        write(repository, 'xxx.txt')
        repository.commit('xxx2')
        repository.push()

    configuration = pathlib.Path(os.path.join(repository.path, '.git', 'config')).read_text(encoding = 'utf-8')

    assert run.call_count > 0
    assert all('ghu_xxx' not in ' '.join(call.args[0]) for call in run.call_args_list)
    assert all(header in call.kwargs['env'].values() for call in run.call_args_list)
    assert 'ghu_xxx' not in configuration
    assert 'x-access-token' not in configuration

@pytest.mark.parametrize('source', SOURCES_IGNORED)
def test_repository_ignored_backup(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    remote: pathlib.Path,
    source: str
) -> None:

    repository = create(remote, pathlib.Path(os.path.join(tmp_path, 'clone')))

    if source == 'vault':

        write(repository, '.gitignore', 'raw/\n')

    else:

        configuration = pathlib.Path(os.path.join(tmp_path, 'configuration'))
        file = pathlib.Path(os.path.join(configuration, 'git', 'ignore'))
        file.parent.mkdir(parents = True, exist_ok = True)
        file.write_text('*.json\n', encoding = 'utf-8')
        monkeypatch.setenv('XDG_CONFIG_HOME', str(configuration))

    raw = pathlib.Path(os.path.join(repository.path, 'raw'))
    raw.mkdir()
    pathlib.Path(os.path.join(raw, 'xxx.json')).write_text('[]\n', encoding = 'utf-8')
    threadvault.vault.state.save(repository.path, {'CXXX1': 'xxx'})

    assert repository.commit('xxx')

    repository.push()
    repository.refresh()

    assert pathlib.Path(os.path.join(raw, 'xxx.json')).read_text(encoding = 'utf-8') == '[]\n'
    assert threadvault.vault.state.load(repository.path) == {'CXXX1': 'xxx'}
