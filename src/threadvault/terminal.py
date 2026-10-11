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
import webbrowser

import slack_bolt.error
import slack_sdk.errors

import threadvault.backup.runner
import threadvault.configuration
import threadvault.customisation
import threadvault.encryption
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.github.token
import threadvault.product
import threadvault.slack.api
import threadvault.slack.application
import threadvault.storage
import threadvault.vault.repository
import threadvault.vault.state

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
    manifest = commands.add_parser('manifest', help = 'print the manifest for creating the Slack app')
    manifest.set_defaults(handler = _manifest)
    doctor = commands.add_parser('doctor', help = 'check the settings, Slack, git, GitHub and the destination')
    doctor.set_defaults(handler = _doctor)
    setup = commands.add_parser('setup', help = 'create the Slack app, register the GitHub App and choose the owner, writing the settings file')
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

        print(f'error: {error}', file = sys.stderr)

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

        print(f'error: {error}', file = sys.stderr)

        return 1

    print(f'Connected to GitHub as {login}')

    return 0

def _start(
    _: argparse.Namespace
) -> int:

    try:

        settings = threadvault.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'threadvault_owner_id', 'github_app_client_id', 'github_app_slug')

        with contextlib.suppress(KeyboardInterrupt): threadvault.slack.application.serve(settings)

    except (threadvault.configuration.ConfigurationError, threadvault.slack.application.LockError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, slack_bolt.error.BoltError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

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

        print(f'ok: settings ({threadvault.configuration.locate()})')

        identity = threadvault.slack.api.connect(settings.slack_bot_token).auth_test()

        print(f"ok: Slack: {identity.get('url', '')}")
        print(f'ok: git {threadvault.vault.repository.verify()}')

        cipher = threadvault.encryption.SecretCipher(threadvault.encryption.load(settings.threadvault_secret_key, settings.threadvault_data_directory))
        database = threadvault.storage.Database(pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.storage.DATABASE_FILE)))

        try:

            manager = threadvault.github.token.TokenManager(database, cipher, settings.github_app_client_id)

            if lenient and not manager.connected():

                print('next: with the Slack app running, connect GitHub and choose the destination in App Home')

                return 0

            token = manager.acquire(datetime.datetime.now(datetime.UTC))

            print(f"ok: GitHub: {threadvault.github.rest.user(token)['login']}")

            repository = threadvault.customisation.SettingsIO(database).load(identity.get('team_id', '')).repository_name

        finally:

            database.close()

        if lenient and repository is None:

            print('next: with the Slack app running, choose the destination in App Home')

            return 0

        if repository is None: raise threadvault.backup.runner.VaultError('No destination is chosen yet')

        found = threadvault.github.rest.repository(token, repository)

        if found is None: raise threadvault.backup.runner.VaultError(f'{repository} does not exist')
        if not found['private']: raise threadvault.backup.runner.VaultError(f'{repository} is public')

    except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError, threadvault.vault.repository.GitError, threadvault.encryption.SecretKeyError, threadvault.storage.DatabaseError, threadvault.github.token.TokenError, threadvault.github.rest.GitHubError, threadvault.backup.runner.VaultError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    print(f'ok: destination: {repository}')

    return 0

def _setup(
    _: argparse.Namespace
) -> int:

    try:

        _create(); _register(); _appoint()

    except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    except (EOFError, KeyboardInterrupt):

        print('\nerror: Setup was stopped', file = sys.stderr)

        return 1

    return _check(lenient = True)

def _create() -> None:

    settings = threadvault.configuration.load()
    manifest = json.loads(importlib.resources.files('threadvault.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))
    url = f'https://api.slack.com/apps?new_app=1&manifest_json={urllib.parse.quote(json.dumps(manifest, separators = (',', ':')))}'

    print(f'Create the Slack app from its manifest: {url}')
    print('Choose the workspace, create the app and install it. Then copy the Bot User OAuth Token in OAuth & Permissions, and generate an App-Level Token with the connections:write scope in Basic Information.', flush = True)
    webbrowser.open(url)

    while True:

        bot, app = _ask('Bot User OAuth Token', settings.slack_bot_token, secret = True), _ask('App-Level Token', settings.slack_app_token, secret = True)

        try: identity = _identify(bot, app)
        except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: print(f'error: {error}', file = sys.stderr)
        else: break

    threadvault.configuration.save({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app})

    print(f"ok: Slack: {identity.get('url', '')}")

def _identify(
    bot: str,
    app: str
) -> slack_sdk.web.SlackResponse:

    threadvault.configuration.load({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app}).require('slack_bot_token', 'slack_app_token')
    client = threadvault.slack.api.connect(bot)
    identity = client.auth_test()
    client.apps_connections_open(app_token = app)

    return identity

def _register() -> None:

    settings = threadvault.configuration.load()
    identity = threadvault.slack.api.connect(settings.slack_bot_token).auth_test()
    organisation = _ask('GitHub organisation to own the vault, or nothing for your own account', '', secret = False)
    query = urllib.parse.urlencode({'name': f"ThreadVault for {identity.get('team', '')}", 'url': identity.get('url', ''), 'public': 'false', 'webhook_active': 'false', 'contents': 'write', 'administration': 'write', 'metadata': 'read'})
    url = f'https://github.com/organizations/{urllib.parse.quote(organisation)}/settings/apps/new?{query}' if organisation else f'https://github.com/settings/apps/new?{query}'

    print(f'Register the GitHub App: {url}')
    print('Also check Enable Device Flow, create the GitHub App and copy its Client ID. Its slug ends the address of its public page, https://github.com/apps/<slug>. Then install it on the account that is to own the vault.', flush = True)
    webbrowser.open(url)

    while True:

        client, slug = _ask('Client ID', settings.github_app_client_id, secret = False), _ask('Slug', settings.github_app_slug, secret = False)

        try: _confirm(client, slug)
        except (threadvault.configuration.ConfigurationError, threadvault.github.oauth.OAuthError) as error: print(f'error: {error}', file = sys.stderr)
        else: break

    threadvault.configuration.save({'GITHUB_APP_CLIENT_ID': client, 'GITHUB_APP_SLUG': slug})

    print(f'ok: GitHub App: {slug}')

def _confirm(
    client: str,
    slug: str
) -> None:

    threadvault.configuration.load({'GITHUB_APP_CLIENT_ID': client, 'GITHUB_APP_SLUG': slug}).require('github_app_client_id', 'github_app_slug')
    threadvault.github.oauth.request(client)

def _appoint() -> None:

    settings = threadvault.configuration.load()
    client = threadvault.slack.api.connect(settings.slack_bot_token)

    print('Copy the member ID of the owner in Slack: open the profile, choose the ⋮ button and Copy member ID.', flush = True)

    while True:

        owner = _ask('Member ID of the owner', settings.threadvault_owner_id, secret = False)

        try: name = _name(client, owner)
        except (threadvault.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: print(f'error: {error}', file = sys.stderr)
        else: break

    while True:

        admins = _ask('Member IDs of other admins, separated by commas', ','.join(sorted(settings.threadvault_admin_ids)), secret = False)

        try: threadvault.configuration.load({'THREADVAULT_ADMIN_IDS': admins})
        except threadvault.configuration.ConfigurationError as error: print(f'error: {error}', file = sys.stderr)
        else: break

    threadvault.configuration.save({'THREADVAULT_OWNER_ID': owner, 'THREADVAULT_ADMIN_IDS': admins})

    print(f'ok: owner: {name}')

def _name(
    client: slack_sdk.web.WebClient,
    user: str
) -> str:

    threadvault.configuration.load({'THREADVAULT_OWNER_ID': user}).require('threadvault_owner_id')
    entry = client.users_info(user = user).get('user', {})

    if entry.get('is_bot') or entry.get('deleted'): raise threadvault.configuration.ConfigurationError(f'{user} is not a person in the workspace')

    profile: dict[str, str] = entry.get('profile', {})

    return profile.get('display_name') or profile.get('real_name') or entry.get('name') or user

def _ask(
    question: str,
    current: str,
    *,
    secret: bool
) -> str:

    hint = (' [keep current]' if secret else f' [{current}]') if current else ''
    answer = (getpass.getpass if secret else input)(f'{question}{hint}: ')

    return answer.strip() or current
