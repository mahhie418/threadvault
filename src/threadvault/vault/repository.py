"""Git commands on the clone of the vault, apart from the git settings of the machine."""

import base64
import collections.abc
import os
import pathlib
import shutil
import subprocess

VERSION_MINIMUM = (2, 31)

TIMEOUT_LIMIT = 600.
RETRY_LIMIT = 3

class GitError(Exception):

    """Raised when git is missing or too old, or a git command fails."""

def verify() -> str:

    """Checks that git is installed and new enough for `Repository`.

    Returns:
        The version of git, as git --version writes it.

    Raises:
        GitError: git is missing or older than `VERSION_MINIMUM`.
    """

    version = _run([_locate(), '--version'], pathlib.Path.cwd(), dict(os.environ)).strip().removeprefix('git version ')
    numbers = tuple(int(part) for part in version.split('.')[:2] if part.isdigit())

    if numbers < VERSION_MINIMUM: raise GitError(f'git {VERSION_MINIMUM[0]}.{VERSION_MINIMUM[1]} or newer is needed, but this is git {version}')

    return version

class Repository:

    """A clone of the vault, worked on by git apart from the settings of the machine.

    Every command takes its settings from the environment, so that no
    credential helper, hook, signing or line ending conversion of the machine
    applies, and housekeeping runs before the command returns. The token
    reaches GitHub only in an HTTP header set in the environment, never in
    the command line, the address of the remote or .git/config. It is asked
    for again for every command, so that a long run can use a refreshed one.

    Attributes:
        path: Working tree of the clone.
    """

    def __init__(
        self,
        path: pathlib.Path,
        *,
        token: collections.abc.Callable[[], str] | None,
        name: str,
        email: str
    ) -> None:

        """Prepares the commands; nothing runs yet.

        Args:
            path: Working tree of the clone, which may not exist yet.
            token: Function that gives a GitHub token for HTTPS remotes,
                   or None for other remotes.
            name: Name of the author of the commits.
            email: Email address of the author of the commits.
        """

        self.path = path

        self._token = token
        self._name = name
        self._email = email

    def clone(
        self,
        url: str
    ) -> None:

        """Clones the remote into `path`.

        Files of earlier commits are left on the remote until git needs them.

        Args:
            url: Address of the remote.

        Raises:
            GitError: git failed.
        """

        self.path.parent.mkdir(parents = True, exist_ok = True)

        self._git('clone', '--filter=blob:none', '--', url, str(self.path), directory = self.path.parent)

    def refresh(
        self
    ) -> None:

        """Makes the working tree match the branch on the remote, dropping every local change.

        Raises:
            GitError: git failed.
        """

        self._git('fetch', '--prune', 'origin')
        self._git('reset', '--hard', '@{upstream}')
        self._git('clean', '-ffdx')

    def commit(
        self,
        message: str
    ) -> bool:

        """Commits every change in the working tree.

        Args:
            message: Message of the commit.

        Returns:
            Whether there was a change to commit.

        Raises:
            GitError: git failed.
        """

        self._git('add', '--all')

        if not self._git('status', '--porcelain'): return False

        self._git('commit', '--quiet', '--message', message)

        return True

    def push(
        self
    ) -> None:

        """Pushes the branch, rebasing it on the remote when the remote has moved on.

        A rejected push is tried again up to `RETRY_LIMIT` times.

        Raises:
            GitError: The push failed, or the rebase met a conflict.
        """

        for _ in range(RETRY_LIMIT):

            try: self._git('push', 'origin', 'HEAD'); return
            except GitError: self._git('fetch', 'origin')

            try: self._git('rebase', '@{upstream}')
            except GitError: self._git('rebase', '--abort'); raise

        self._git('push', 'origin', 'HEAD')

    def head(
        self
    ) -> str:

        """Gives the commit that the working tree is at.

        Returns:
            The full ID of the commit.

        Raises:
            GitError: git failed.
        """

        return self._git('rev-parse', 'HEAD').strip()

    def _git(
        self,
        *arguments: str,
        directory: pathlib.Path | None = None
    ) -> str:

        return _run([_locate(), *arguments], directory or self.path, _isolate(self._token() if self._token else None, self._name, self._email))

def _locate() -> str:

    if (executable := shutil.which('git')) is None: raise GitError('git is not installed')

    return executable

def _isolate(
    token: str | None,
    name: str,
    email: str
) -> dict[str, str]:

    settings = [
        ('credential.helper', ''),
        ('core.autocrlf', 'false'),
        ('core.longpaths', 'true'),
        ('core.quotepath', 'false'),
        ('core.precomposeunicode', 'true'),
        ('core.hooksPath', os.devnull),
        ('commit.gpgsign', 'false'),
        ('gc.autoDetach', 'false'),
        ('maintenance.autoDetach', 'false'),
        ('user.name', name),
        ('user.email', email)
    ]

    if token:

        credential = base64.b64encode(f'x-access-token:{token}'.encode()).decode('ascii')
        settings += [('http.https://github.com/.extraheader', ''), ('http.https://github.com/.extraheader', f'Authorization: Basic {credential}')]

    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')} | {'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never', 'GIT_LFS_SKIP_SMUDGE': '1', 'GIT_CONFIG_COUNT': str(len(settings))}

    for index, (key, value) in enumerate(settings): environment |= {f'GIT_CONFIG_KEY_{index}': key, f'GIT_CONFIG_VALUE_{index}': value}

    return environment

def _run(
    command: list[str],
    directory: pathlib.Path,
    environment: dict[str, str]
) -> str:

    try: result = subprocess.run(command, cwd = directory, env = environment, capture_output = True, encoding = 'utf-8', errors = 'replace', timeout = TIMEOUT_LIMIT, check = False)
    except subprocess.TimeoutExpired: raise GitError(f'git {command[1]} took longer than {TIMEOUT_LIMIT:.0f} seconds') from None

    if result.returncode: raise GitError(f'git {command[1]} failed: {result.stderr.strip()}')

    return result.stdout
