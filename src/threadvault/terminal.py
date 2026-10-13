"""Command-line entry point."""

import argparse
import contextlib
import dataclasses
import datetime
import getpass
import importlib.resources
import json
import os
import pathlib
import sys
import urllib.parse

import rich.console
import rich.style
import rich.text
import slack_bolt.error
import slack_sdk.errors

import threadvault.autostart
import threadvault.backup.runner
import threadvault.configuration
import threadvault.customisation
import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.github.token
import threadvault.product
import threadvault.shortener
import threadvault.slack.api
import threadvault.slack.application
import threadvault.storage
import threadvault.vault.repository
import threadvault.vault.state

_STATUS_STYLES = {'OK': 'bold green', 'NEXT': 'bold cyan', 'WARNING': 'bold yellow', 'ERROR': 'bold red'}

def main(
    arguments: list[str] | None = None
) -> int:

    """Runs the command.

    Args:
        arguments: Command-line arguments without the program name.
                   When None, the arguments of the current process are used.

    Returns:
        The exit status of the command.

    Raises:
        SystemExit: argparse handled the arguments itself:
                    it printed help or the version (status 0), or a usage error (status 2).
    """

    parser = _build()
    namespace = parser.parse_args(arguments)

    return namespace.handler(namespace)

def _build() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog = threadvault.product.COMMAND, description = threadvault.product.SUMMARY)
    parser.add_argument('--version', action = 'version', version = f'%(prog)s {threadvault.product.VERSION}')

    commands = parser.add_subparsers(title = 'commands', metavar = '<command>', required = True)
    key = commands.add_parser('key', help = 'print a new key for THREADVAULT_SECRET_KEY')
    key.set_defaults(handler = _key)
    backup = commands.add_parser('backup', help = 'back up the workspace once, into a local directory or a GitHub repository')
    backup.set_defaults(handler = _backup)
    destination = backup.add_mutually_exclusive_group(required = True)
    destination.add_argument('--out', type = pathlib.Path, help = 'directory of the vault', metavar = 'DIR')
    destination.add_argument('--repo', help = 'GitHub repository of the vault, created as private when missing', metavar = 'OWNER/NAME')
    connection = commands.add_parser('connect', help = 'connect GitHub with the device flow of the GitHub App')
    connection.set_defaults(handler = _connect)
    start = commands.add_parser('start', help = 'run the Slack app until it is stopped')
    start.set_defaults(handler = _start)
    start.add_argument('--log', type = pathlib.Path, help = 'file to append the output to', metavar = 'FILE')
    stop = commands.add_parser('stop', help = 'stop the Slack app and stop it from starting at login')
    stop.set_defaults(handler = _stop)
    manifest = commands.add_parser('manifest', help = 'print the manifest for creating the Slack app')
    manifest.set_defaults(handler = _manifest)
    doctor = commands.add_parser('doctor', help = 'check the settings, Slack, git, GitHub and the destination')
    doctor.set_defaults(handler = _doctor)
    setup = commands.add_parser('setup', help = 'create the Slack app, register the GitHub App, choose the owner and start the Slack app at login, writing the settings file')
    setup.set_defaults(handler = _setup)

    return parser

def _key(
    _: argparse.Namespace
) -> int:

    print(threadvault.encryption.generate())

    return 0

def _backup(
    namespace: argparse.Namespace
) -> int:

    now = datetime.datetime.now(datetime.UTC)
    repository: str | None = namespace.repo

    try:

        settings = threadvault.configuration.load()

        if repository is None: settings.require('slack_bot_token')
        else: settings.require('slack_bot_token', 'github_app_client_id')

        client = threadvault.slack.api.connect(settings.slack_bot_token)
        database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))

        try:

            workspace = dataclasses.replace(threadvault.customisation.SettingsIO(database).load(client.auth_test().get('team_id', '')), repository_name = repository)

            if repository is None:

                results = threadvault.backup.runner.run(client, namespace.out, workspace, days = settings.threadvault_lookback_days, limit = settings.threadvault_deletions_maximum, now = now)

            else:

                cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
                manager = threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id)
                directory = pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.backup.runner.VAULTS_DIRECTORY, *repository.split('/')))
                results, _ = threadvault.backup.runner.publish(client, workspace, directory = directory, full_name = repository, token = lambda: manager.acquire(datetime.datetime.now(datetime.UTC)), days = settings.threadvault_lookback_days, limit = settings.threadvault_deletions_maximum, now = now)

        finally:

            database.close()

    except (threadvault.configuration.ConfigurationError, threadvault.customisation.SettingInvalidError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, threadvault.vault.state.StateError, threadvault.vault.repository.GitError, threadvault.github.token.TokenError, threadvault.github.rest.GitHubError, threadvault.backup.runner.VaultError, threadvault.backup.runner.LockError, slack_sdk.errors.SlackApiError) as error:

        _report('ERROR', str(error))

        return 1

    for result in results: print(f'{result.directory}: {result.messages} messages, {result.deleted} deleted, {result.withheld} withheld, {result.files} files, {result.failures} failures')

    return 0

def _connect(
    _: argparse.Namespace
) -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('github_app_client_id')
        cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
        code = threadvault.github.oauth.request(settings.github_app_client_id)

        print(f'Open {code.verification_uri} and enter {code.user_code}', flush = True)

        tokens = threadvault.github.oauth.poll(settings.github_app_client_id, code)
        database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))

        try: threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id).save(tokens)
        finally: database.close()

        login = threadvault.github.rest.user(tokens.access_token)['login']

    except (threadvault.configuration.ConfigurationError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, threadvault.github.oauth.OAuthError, threadvault.github.rest.GitHubError) as error:

        _report('ERROR', str(error))

        return 1

    _report('OK', f'GitHub: {login}')

    return 0

def _start(
    namespace: argparse.Namespace
) -> int:

    log: pathlib.Path | None = namespace.log

    if log is None: return _serve()

    log.parent.mkdir(parents = True, exist_ok = True)

    with log.open('a', encoding = 'utf-8', buffering = 1) as file, contextlib.redirect_stdout(file), contextlib.redirect_stderr(file): return _serve()

def _serve() -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'threadvault_owner_id', 'github_app_client_id', 'github_app_slug')

        with contextlib.suppress(KeyboardInterrupt): threadvault.slack.application.serve(settings)

    except (threadvault.configuration.ConfigurationError, threadvault.slack.application.LockError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, slack_bolt.error.BoltError) as error:

        _report('ERROR', str(error))

        return 1

    return 0

def _stop(
    _: argparse.Namespace
) -> int:

    try:

        registration = threadvault.autostart.unregister()

    except threadvault.autostart.AutostartError as error:

        _report('ERROR', str(error))

        return 1

    _report('OK', f'autostart: removed {registration}' if registration else 'autostart: not registered')

    return 0

def _manifest(
    _: argparse.Namespace
) -> int:

    print(importlib.resources.files('threadvault.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'), end = '')

    return 0

def _doctor(
    _: argparse.Namespace
) -> int:

    return _check(lenient = False)

def _check(
    *,
    lenient: bool
) -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'threadvault_owner_id', 'github_app_client_id', 'github_app_slug')

        _report('OK', f'settings ({threadvault.configuration.locate()})')

        identity = threadvault.slack.api.connect(settings.slack_bot_token).auth_test()

        _report('OK', f"Slack: {identity.get('url', '')}")
        _report('OK', f'git {threadvault.vault.repository.verify()}')

        cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
        database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))

        try:

            manager = threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id)

            if lenient and not manager.connected():

                _report('NEXT', 'once the Slack app is running, connect GitHub and choose the destination in its App Home')

                return 0

            token = manager.acquire(datetime.datetime.now(datetime.UTC))

            _report('OK', f"GitHub: {threadvault.github.rest.user(token)['login']}")

            repository = threadvault.customisation.SettingsIO(database).load(identity.get('team_id', '')).repository_name

        finally:

            database.close()

        if lenient and repository is None:

            _report('NEXT', 'once the Slack app is running, choose the destination in its App Home')

            return 0

        if repository is None: raise threadvault.backup.runner.VaultError('No destination is chosen yet')

        found = threadvault.github.rest.repository(token, repository)

        if found is None: raise threadvault.backup.runner.VaultError(f'{repository} does not exist')
        if not found['private']: raise threadvault.backup.runner.VaultError(f'{repository} is public')

    except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError, threadvault.vault.repository.GitError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, threadvault.github.token.TokenError, threadvault.github.rest.GitHubError, threadvault.backup.runner.VaultError) as error:

        _report('ERROR', str(error))

        return 1

    _report('OK', f'destination: {repository}')

    return 0

def _setup(
    _: argparse.Namespace
) -> int:

    print()
    _console().print(rich.text.Text.assemble(('ThreadVault', 'bold'), ' ', (f'(Version: {threadvault.product.VERSION})', 'dim')))

    try:

        with threadvault.shortener.Shortener() as shortener:

            if shortener.failure is not None: _report('WARNING', f'Short links are not available on this computer ({shortener.failure}), so the full addresses follow', blank = True)

            _create(shortener); _register(shortener); _appoint()

        print()

        if (status := _check(lenient = True)) == 0: _autostart()

    except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError, threadvault.autostart.AutostartError) as error:

        _report('ERROR', str(error), blank = True)

        return 1

    except (EOFError, KeyboardInterrupt):

        _report('ERROR', 'Setup was stopped', blank = True)

        return 1

    finally:

        print()

    return status

def _create(
    shortener: threadvault.shortener.Shortener
) -> None:

    settings = threadvault.configuration.load()
    manifest = json.loads(importlib.resources.files('threadvault.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))
    url = f'https://api.slack.com/apps?new_app=1&manifest_json={urllib.parse.quote(json.dumps(manifest, separators = (',', ':')))}'

    print('\nOpen the link below to create the Slack app. Its settings are filled in from the manifest.')
    _link(shortener.shorten('slack', url))
    _steps('Select the workspace, then follow the pages to create the app.', 'Select Install to Workspace and allow the access the app asks for.', 'In OAuth & Permissions, copy the Bot User OAuth Token (it starts with xoxb-).', 'In Basic Information, under App-Level Tokens, generate a token with the connections:write scope and copy it (it starts with xapp-).')

    while True:

        print('\nPaste the Bot User OAuth Token and the App-Level Token. They stay hidden as you type.\n', flush = True)
        bot, app = _ask('Bot User OAuth Token', settings.slack_bot_token, secret = True), _ask('App-Level Token', settings.slack_app_token, secret = True)

        try: identity = _identify(bot, app)
        except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: _report('ERROR', str(error), blank = True)
        else: break

    threadvault.configuration.save({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app})

    _report('OK', f"Slack: {identity.get('url', '')}", blank = True)

def _identify(
    bot: str,
    app: str
) -> slack_sdk.web.SlackResponse:

    threadvault.configuration.load({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app}).require('slack_bot_token', 'slack_app_token')
    client = threadvault.slack.api.connect(bot)
    identity = client.auth_test()
    client.apps_connections_open(app_token = app)

    return identity

def _register(
    shortener: threadvault.shortener.Shortener
) -> None:

    settings = threadvault.configuration.load()
    identity = threadvault.slack.api.connect(settings.slack_bot_token).auth_test()

    print()

    if _agree('Keep the vault in a GitHub organisation instead of your personal account?', default = False): organisation = _ask('Organisation name, as in https://github.com/<name>', '', secret = False)
    else: organisation = ''

    query = urllib.parse.urlencode({'name': f"ThreadVault for {identity.get('team', '')}", 'url': identity.get('url', ''), 'public': 'false', 'webhook_active': 'false', 'contents': 'write', 'administration': 'write', 'metadata': 'read'})
    url = f'https://github.com/organizations/{urllib.parse.quote(organisation)}/settings/apps/new?{query}' if organisation else f'https://github.com/settings/apps/new?{query}'

    print('\nOpen the link below to register the GitHub App. Its settings are filled in.')
    _link(shortener.shorten('github', url))
    _steps('Tick Enable Device Flow.', 'Select Create GitHub App, then copy the Client ID.', 'Copy the app slug: the last part of the public link, https://github.com/apps/<slug>.', 'Select Install App and install it on the account that keeps the vault.')

    while True:

        print('\nPaste the Client ID and the app slug.\n')
        client, slug = _ask('Client ID', settings.github_app_client_id, secret = False), _ask('App slug', settings.github_app_slug, secret = False)

        try: _confirm(client, slug)
        except (threadvault.configuration.ConfigurationError, threadvault.github.oauth.OAuthError) as error: _report('ERROR', str(error), blank = True)
        else: break

    threadvault.configuration.save({'GITHUB_APP_CLIENT_ID': client, 'GITHUB_APP_SLUG': slug})

    _report('OK', f'GitHub App: {slug}', blank = True)

def _confirm(
    client: str,
    slug: str
) -> None:

    threadvault.configuration.load({'GITHUB_APP_CLIENT_ID': client, 'GITHUB_APP_SLUG': slug}).require('github_app_client_id', 'github_app_slug')
    threadvault.github.oauth.request(client)

def _appoint() -> None:

    settings = threadvault.configuration.load()
    client = threadvault.slack.api.connect(settings.slack_bot_token)

    print('\nChoose who owns ThreadVault in Slack, and copy their member ID.')
    _steps('In Slack, open their profile.', 'Select ⋮ (More), then Copy member ID.')

    while True:

        print()
        owner = _ask('Member ID of the owner', settings.threadvault_owner_id, secret = False)

        try: name = _name(client, owner)
        except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: _report('ERROR', str(error), blank = True)
        else: break

    threadvault.configuration.save({'THREADVAULT_OWNER_ID': owner})

    _report('OK', f'owner: {name}', blank = True)

def _name(
    client: slack_sdk.web.WebClient,
    user: str
) -> str:

    threadvault.configuration.load({'THREADVAULT_OWNER_ID': user}).require('threadvault_owner_id')
    entry = client.users_info(user = user).get('user', {})

    if entry.get('is_bot') or entry.get('deleted'): raise threadvault.configuration.ConfigurationError(f'{user} is not a person in the workspace')

    profile: dict[str, str] = entry.get('profile', {})

    return profile.get('display_name') or profile.get('real_name') or entry.get('name') or user

def _autostart() -> None:

    if sys.platform in threadvault.autostart.PLATFORMS: print()

    if sys.platform not in threadvault.autostart.PLATFORMS or not _agree('Start the Slack app automatically when you log in?', default = True):

        _report('NEXT', f"run '{threadvault.product.COMMAND} start' to start the Slack app", blank = True)

        return

    log = pathlib.Path(os.path.join(threadvault.configuration.load().threadvault_data_directory, 'start.log'))

    _report('OK', f'autostart: {threadvault.autostart.register(log)}', blank = True)

def _ask(
    question: str,
    current: str,
    *,
    secret: bool
) -> str:

    hint = (' [keep current]' if secret else f' [{current}]') if current else ''
    answer = (getpass.getpass if secret else input)(f'{question}{hint}: ')

    return answer.strip() or current

def _agree(
    question: str,
    *,
    default: bool
) -> bool:

    hint = '[Y/n]' if default else '[y/N]'
    answer = input(f'{question} {hint}: ').strip().lower()

    return answer in {'y', 'yes'} if answer else default

def _steps(
    *steps: str
) -> None:

    console = _console()
    console.print()

    for number, step in enumerate(steps, start = 1): console.print(rich.text.Text.assemble((f'{number}.', 'bold'), f' {step}'))

def _link(
    url: str
) -> None:

    console = _console()
    console.print()
    console.print(rich.text.Text.assemble('>> ', (url, rich.style.Style(underline = True, link = url))))

def _report(
    status: str,
    message: str,
    *,
    blank: bool = False
) -> None:

    _console(stderr = status in {'WARNING', 'ERROR'}).print(rich.text.Text.assemble('\n' if blank else '', (f'[{status}]', _STATUS_STYLES[status]), f' {message}'))

def _console(
    *,
    stderr: bool = False
) -> rich.console.Console:

    return rich.console.Console(stderr = stderr, soft_wrap = True, highlight = False, markup = False, emoji = False)
