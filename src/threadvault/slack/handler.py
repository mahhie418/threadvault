"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import collections.abc
import dataclasses
import datetime
import http
import json
import logging
import os
import pathlib
import threading
import typing
import zoneinfo

import slack_bolt
import slack_sdk.errors

import threadvault.backup.backlog
import threadvault.backup.runner
import threadvault.configuration
import threadvault.customisation
import threadvault.github.oauth
import threadvault.github.rest
import threadvault.github.token
import threadvault.journal
import threadvault.localisation
import threadvault.product
import threadvault.schedule
import threadvault.slack.permission
import threadvault.slack.view
import threadvault.storage
import threadvault.vault.repository
import threadvault.vault.state
import threadvault.worker

_LOGGER = logging.getLogger(__name__)

def register(
    application: slack_bolt.App,
    settings: threadvault.configuration.Settings,
    database: threadvault.storage.Database,
    manager: threadvault.github.token.TokenManager
) -> collections.abc.Callable[[str, datetime.datetime], None]:

    """Registers the listeners of the app.

    The listeners call Slack with the client of the app, which holds the bot
    token of the one workspace, rather than with a client per request. What
    a view shows depends on the role of its viewer, and each view is in the
    language of the Slack locale of its viewer. Only the owner and the admins
    allowed to operate the app act in it, and only the owner changes the
    permissions of the admins and transfers the ownership to an admin, as
    `threadvault.slack.permission.restrict` makes sure. When the permissions
    or the ownership change, both the admin and the owner hear of it by
    direct message, and the owner and the allowed admins hear by direct
    message when GitHub is connected or disconnected, or when the destination
    is chosen or created. A backup started from the App Home runs in the
    background, one at a time, as `threadvault.worker.Worker` makes sure, and
    the App Home of whoever started it shows the backup while it runs. Every
    App Home shows how the last backup ended, and the owner and the allowed
    admins hear by direct message when a backup fails. A resynchronisation is
    a backup that fetches every channel in full and deletes nothing. Once the
    destination is chosen, the daily backup runs at the time in the settings
    of the workspace, and one missed while the app was stopped runs as soon
    as the app runs again. The settings say whether it runs and its time and
    time zone, which the Markdown follows too, which channels backups cover
    and whether the bot joins the public ones first, whether they save
    attached files and up to which size, and the language of the Markdown.

    A reply to a thread marks the thread, and the next backup fetches the
    marked threads again, so that it does not miss a reply to a thread older
    than the days that it fetches. An edited or deleted message marks its
    thread, or its day when it is not a reply, for the same reason. The
    marks go once the backup succeeds.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the settings, the backups and the schedule of each workspace.
        manager: GitHub tokens of the deployment.

    Returns:
        The function that starts the daily backup once it is due, given the
        workspace ID and the current time.
    """

    store = threadvault.customisation.SettingsIO(database)
    journal = threadvault.journal.RunIO(database)
    calendar = threadvault.schedule.ScheduleIO(database)
    backlog = threadvault.backup.backlog.BacklogIO(database)
    cache = threadvault.github.rest.RepositoryCache()
    worker = threadvault.worker.Worker(detach)
    guard = [threadvault.slack.permission.restrict(settings, store, frozenset({'owner'}))]

    def choose(
        user: str
    ) -> threadvault.configuration.Language:

        entry: dict[str, typing.Any] = application.client.users_info(user = user, include_locale = True).get('user', {})

        return threadvault.localisation.choose(entry.get('locale'), settings.threadvault_language_display)

    def inspect() -> threadvault.slack.view.GitHubState:

        if not manager.connected(): return 'disconnected'

        try:

            installations = threadvault.github.rest.installations(manager.acquire(datetime.datetime.now(datetime.UTC)))

        except threadvault.github.token.TokenError as error:

            _LOGGER.warning('GitHub must be connected again: %s', error)

            return 'expired'

        except threadvault.github.rest.GitHubError as error:

            if error.status == http.HTTPStatus.UNAUTHORIZED: return 'expired'

            _LOGGER.warning('GitHub App installations were not checked: %s', error)

            return 'connected'

        return 'connected' if installations else 'uninstalled'

    def plan(
        team: str,
        now: datetime.datetime
    ) -> datetime.datetime | None:

        workspace = store.load(team)
        planned = calendar.load(team)

        if not workspace.schedule_enabled or workspace.repository_name is None: return None
        if planned is None: planned = threadvault.schedule.follow(now, workspace.schedule_time, workspace.workspace_timezone); calendar.save(team, planned)

        return planned

    def refresh(
        team: str,
        user: str
    ) -> None:

        workspace = store.load(team)

        application.client.views_publish(user_id = user, view = threadvault.slack.view.home(github = inspect(), destination = workspace.repository_name, running = worker.busy(), last = journal.load(team), planned = plan(team, datetime.datetime.now(datetime.UTC)), role = threadvault.slack.permission.role(settings, workspace, user), language = choose(user)))

    def show(
        modal: str,
        view: dict[str, typing.Any]
    ) -> None:

        try: application.client.views_update(view_id = modal, view = view)
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Modal not updated, perhaps because it was closed: %s', error)

    def tell(
        recipient: str,
        key: str,
        **values: str
    ) -> None:

        try: application.client.chat_postMessage(channel = recipient, text = threadvault.localisation.translate(key, choose(recipient), **values))
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Direct message to %s not sent: %s', recipient, error)

    def notify(
        team: str,
        key: str,
        **values: str
    ) -> None:

        workspace = store.load(team)

        for recipient in sorted(admin for admin in threadvault.slack.permission.admins(settings, workspace) if threadvault.slack.permission.role(settings, workspace, admin) in ('owner', 'operator')): tell(recipient, key, **values)

    def link(
        team: str,
        user: str,
        modal: str,
        language: threadvault.configuration.Language
    ) -> None:

        try:

            code = threadvault.github.oauth.request(settings.github_app_client_id)
            show(modal, threadvault.slack.view.connect(code = code, language = language))
            manager.save(threadvault.github.oauth.poll(settings.github_app_client_id, code))

        except threadvault.github.oauth.OAuthError as error:

            show(modal, threadvault.slack.view.respond(error = error, language = language))

            return

        refresh(team, user)
        show(modal, threadvault.slack.view.respond(error = None, language = language))
        notify(team, 'notice.connection', user = user)

    def index() -> None:

        try: cache.update(manager.acquire(datetime.datetime.now(datetime.UTC)))
        except (threadvault.github.token.TokenError, threadvault.github.rest.GitHubError) as error: _LOGGER.warning('Repositories were not listed: %s', error)

    def settle(
        team: str,
        user: str,
        modal: str,
        repository: str,
        language: threadvault.configuration.Language
    ) -> None:

        try:

            threadvault.customisation.Settings(repository_name = repository)
            found = threadvault.github.rest.repository(manager.acquire(datetime.datetime.now(datetime.UTC)), repository)

        except (threadvault.customisation.SettingInvalidError, threadvault.github.token.TokenError, threadvault.github.rest.GitHubError) as error:

            show(modal, threadvault.slack.view.settle(repository = repository, outcome = 'failure', language = language, message = str(error)))

            return

        if found is None or not found['private']:

            show(modal, threadvault.slack.view.settle(repository = repository, outcome = 'absence' if found is None else 'publicity', language = language))

            return

        store.save(team, dataclasses.replace(store.load(team), repository_name = repository), update_user = user)
        refresh(team, user)
        show(modal, threadvault.slack.view.settle(repository = repository, outcome = 'success', language = language))
        notify(team, 'notice.destination', user = user, repository = repository)

    def gather(
        modal: str,
        language: threadvault.configuration.Language
    ) -> None:

        try:

            installations = threadvault.github.rest.installations(manager.acquire(datetime.datetime.now(datetime.UTC)))

        except (threadvault.github.token.TokenError, threadvault.github.rest.GitHubError) as error:

            show(modal, threadvault.slack.view.establish(repository = '', outcome = 'failure', language = language, message = str(error)))

            return

        show(modal, threadvault.slack.view.propose(accounts = sorted({installation['account']['login'] for installation in installations}, key = str.casefold), language = language))

    def establish(
        team: str,
        user: str,
        modal: str,
        repository: str,
        language: threadvault.configuration.Language
    ) -> None:

        try:

            threadvault.customisation.Settings(repository_name = repository)
            threadvault.github.rest.create(manager.acquire(datetime.datetime.now(datetime.UTC)), repository)

        except (threadvault.customisation.SettingInvalidError, threadvault.github.token.TokenError, threadvault.github.rest.GitHubError) as error:

            show(modal, threadvault.slack.view.establish(repository = repository, outcome = 'failure', language = language, message = str(error)))

            return

        store.save(team, dataclasses.replace(store.load(team), repository_name = repository), update_user = user)
        refresh(team, user)
        show(modal, threadvault.slack.view.establish(repository = repository, outcome = 'success', language = language))
        notify(team, 'notice.creation', user = user, repository = repository)

    def perform(
        team: str,
        user: str | None,
        days: int | None
    ) -> None:

        if user is not None: refresh(team, user)

        workspace = store.load(team)

        if workspace.repository_name is None: return

        directory = pathlib.Path(os.path.join(settings.threadvault_data_directory, threadvault.backup.runner.VAULTS_DIRECTORY, *workspace.repository_name.split('/')))
        now, marks = datetime.datetime.now(datetime.UTC), backlog.load(team)
        commit, reason = None, None

        try: _, commit = threadvault.backup.runner.publish(application.client, workspace, directory = directory, full_name = workspace.repository_name, token = lambda: manager.acquire(datetime.datetime.now(datetime.UTC)), days = days, limit = settings.threadvault_deletions_maximum, now = now, backlog = marks)
        except (threadvault.backup.runner.VaultError, threadvault.backup.runner.LockError, threadvault.github.rest.GitHubError, threadvault.github.token.TokenError, threadvault.vault.repository.GitError, threadvault.vault.state.StateError, slack_sdk.errors.SlackApiError) as error: _LOGGER.warning('Backup failed: %s', error); reason = str(error)
        else: backlog.clear(team, now)

        journal.save(team, threadvault.journal.Run(completion = datetime.datetime.now(datetime.UTC), repository = workspace.repository_name, commit = commit, reason = reason))

        if reason is not None: notify(team, 'notice.failure', message = reason)

    def schedule(
        team: str,
        now: datetime.datetime
    ) -> None:

        planned = plan(team, now)

        if planned is None or now < planned or not worker.start(lambda: perform(team, None, settings.threadvault_lookback_days), lambda: None): return

        workspace = store.load(team)

        calendar.save(team, threadvault.schedule.follow(now, workspace.schedule_time, workspace.workspace_timezone))

    def publish(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if event.get('tab') != 'home' or context.team_id is None: return

        refresh(context.team_id, event['user'])

    def note(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if (team := context.team_id) is None: return

        match event.get('subtype'):

            case 'message_changed': message, edited = event['message'], True
            case 'message_deleted': message, edited = event.get('previous_message', {'ts': event['deleted_ts']}), True
            case _: message, edited = event, False

        thread_ts, now = message.get('thread_ts', message['ts']), datetime.datetime.now(datetime.UTC)

        if thread_ts != message['ts']: backlog.mark(team, event['channel'], thread_ts, now)
        elif edited: backlog.mark(team, event['channel'], datetime.datetime.fromtimestamp(float(message['ts']), datetime.UTC).date(), now)

    def connect(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        language = choose(user)
        opening: dict[str, typing.Any] = application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.connect(code = None, language = language)).get('view', {})

        detach(lambda: link(team, user, opening['id'], language))

    def disconnect(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        manager.delete()
        refresh(context.team_id, context.user_id)
        notify(context.team_id, 'notice.disconnection', user = context.user_id)

        container: dict[str, typing.Any] = body.get('view', {})

        if container.get('type') == 'modal': show(container['id'], threadvault.slack.view.disconnect(language = choose(context.user_id)))

    def install(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.user_id is None: return

        application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.install(slug = settings.github_app_slug, language = choose(context.user_id)))

    def follow(
        ack: slack_bolt.Ack
    ) -> None:

        ack()

    def offer(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        detach(index)
        application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.offer(current = store.load(context.team_id).repository_name, language = choose(context.user_id)))

    def submit(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        repository: str = view['state']['values'][threadvault.slack.view.REPOSITORY_ACTION][threadvault.slack.view.REPOSITORY_ACTION]['selected_option']['value']
        language = choose(user)

        ack(response_action = 'update', view = threadvault.slack.view.settle(repository = repository, outcome = 'check', language = language))
        detach(lambda: settle(team, user, view['id'], repository, language))

    def suggest(
        ack: slack_bolt.Ack,
        payload: dict[str, typing.Any]
    ) -> None:

        ack(options = threadvault.slack.view.suggest(cache.search(payload.get('value', '')) or []))

    def propose(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.user_id is None: return

        language = choose(context.user_id)
        modal = body['view']['id']

        show(modal, threadvault.slack.view.propose(accounts = None, language = language))
        detach(lambda: gather(modal, language))

    def create(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        values = view['state']['values']
        account: str = values[threadvault.slack.view.ACCOUNT_INPUT][threadvault.slack.view.ACCOUNT_INPUT]['selected_option']['value']
        name: str = values[threadvault.slack.view.NAME_INPUT][threadvault.slack.view.NAME_INPUT]['value']
        repository = f'{account}/{name}'
        language = choose(user)

        ack(response_action = 'update', view = threadvault.slack.view.establish(repository = repository, outcome = 'check', language = language))
        detach(lambda: establish(team, user, view['id'], repository, language))

    def launch(
        ack: slack_bolt.Ack,
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        if not worker.start(lambda: perform(team, user, settings.threadvault_lookback_days), lambda: refresh(team, user)): refresh(team, user)

    def resynchronise(
        ack: slack_bolt.Ack,
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        if not worker.start(lambda: perform(team, user, None), lambda: refresh(team, user)): refresh(team, user)

    def configure(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        workspace = store.load(context.team_id)
        entry: dict[str, typing.Any] = application.client.users_info(user = context.user_id).get('user', {})
        zone = workspace.workspace_timezone

        if zone == threadvault.customisation.Settings().workspace_timezone: zone = entry.get('tz') or zone

        application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.configure(workspace = dataclasses.replace(workspace, workspace_timezone = zone), language = choose(context.user_id)))

    def search(
        ack: slack_bolt.Ack,
        payload: dict[str, typing.Any]
    ) -> None:

        query: str = payload.get('value', '')

        ack(options = threadvault.slack.view.suggest(sorted(zone for zone in zoneinfo.available_timezones() if query.casefold() in zone.casefold())))

    def adjust(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        values: dict[str, dict[str, dict[str, typing.Any]]] = view['state']['values']
        elements = {action: element for block in values.values() for action, element in block.items()}
        previous = store.load(team)
        workspace = dataclasses.replace(previous, schedule_enabled = bool(elements[threadvault.slack.view.SCHEDULE_INPUT]['selected_options']), schedule_time = elements[threadvault.slack.view.TIME_INPUT]['selected_time'], workspace_timezone = elements[threadvault.slack.view.TIMEZONE_ACTION]['selected_option']['value'], channel_mode = elements[threadvault.slack.view.MODE_INPUT]['selected_option']['value'], channels_selected = tuple(sorted(elements[threadvault.slack.view.CHANNELS_INPUT].get('selected_conversations', []))), channels_joined = bool(elements[threadvault.slack.view.JOINING_INPUT]['selected_options']), attachments_enabled = bool(elements[threadvault.slack.view.ATTACHMENTS_INPUT]['selected_options']), attachment_size_maximum = int(elements[threadvault.slack.view.SIZE_INPUT]['value']), markdown_language = elements[threadvault.slack.view.LANGUAGE_INPUT]['selected_option']['value'])

        if workspace.channel_mode == 'selected' and not workspace.channels_selected:

            ack(response_action = 'errors', errors = {threadvault.slack.view.CHANNELS_INPUT: threadvault.localisation.translate('settings.channels.missing', choose(user))})

            return

        store.save(team, workspace, update_user = user)

        if (workspace.schedule_enabled, workspace.schedule_time, workspace.workspace_timezone) != (previous.schedule_enabled, previous.schedule_time, previous.workspace_timezone): calendar.save(team, threadvault.schedule.follow(datetime.datetime.now(datetime.UTC), workspace.schedule_time, workspace.workspace_timezone))

        ack()

        refresh(team, user)

    def manage(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        workspace = store.load(context.team_id)
        admins = sorted(threadvault.slack.permission.admins(settings, workspace) - {threadvault.slack.permission.owner(settings, workspace)})

        application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.permit(admins = admins, allowed = workspace.admins_allowed, language = choose(context.user_id)))

    def review(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if context.team_id is None or context.user_id is None: return

        workspace = store.load(context.team_id)
        admins = threadvault.slack.permission.admins(settings, workspace) - {threadvault.slack.permission.owner(settings, workspace)}
        allowed = set(workspace.admins_allowed) & admins
        values: dict[str, dict[str, dict[str, typing.Any]]] = view['state']['values']
        chosen = {option['value'] for block in values.values() for element in block.values() for option in element['selected_options']}
        granted, revoked = sorted(chosen - allowed), sorted(allowed - chosen)
        language = choose(context.user_id)

        if granted or revoked: ack(response_action = 'push', view = threadvault.slack.view.review(granted = granted, revoked = revoked, language = language))
        else: ack(response_action = 'errors', errors = {f'{threadvault.slack.view.ADMINS_INPUT}0': threadvault.localisation.translate('permissions.unchanged', language)})

    def apply(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, owner = context.team_id, context.user_id

        if team is None or owner is None: return

        changes: dict[str, list[str]] = json.loads(view['private_metadata'])
        workspace = store.load(team)
        allowed = (set(workspace.admins_allowed) | set(changes['granted'])) - set(changes['revoked'])

        store.save(team, dataclasses.replace(workspace, admins_allowed = tuple(sorted(allowed))), update_user = owner)
        ack(response_action = 'clear')

        for user in [owner, *changes['granted'], *changes['revoked']]: refresh(team, user)

        for user in changes['granted']:

            tell(user, 'notice.grant', owner = owner, product = threadvault.product.NAME)
            tell(owner, 'notice.grant.done', user = user, product = threadvault.product.NAME)

        for user in changes['revoked']:

            tell(user, 'notice.revocation', owner = owner, product = threadvault.product.NAME)
            tell(owner, 'notice.revocation.done', user = user, product = threadvault.product.NAME)

    def cede(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.user_id is None: return

        application.client.views_open(trigger_id = body['trigger_id'], view = threadvault.slack.view.cede(language = choose(context.user_id)))

    def nominate(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if context.team_id is None or context.user_id is None: return

        workspace = store.load(context.team_id)
        admins = threadvault.slack.permission.admins(settings, workspace) - {threadvault.slack.permission.owner(settings, workspace)}
        successor: str = view['state']['values'][threadvault.slack.view.SUCCESSOR_INPUT][threadvault.slack.view.SUCCESSOR_INPUT]['selected_user']
        language = choose(context.user_id)

        if successor in admins: ack(response_action = 'push', view = threadvault.slack.view.nominate(successor = successor, language = language))
        else: ack(response_action = 'errors', errors = {threadvault.slack.view.SUCCESSOR_INPUT: threadvault.localisation.translate('transfer.invalid', language)})

    def transfer(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, former = context.team_id, context.user_id

        if team is None or former is None: return

        successor: str = view['private_metadata']
        workspace = store.load(team)
        allowed = (set(workspace.admins_allowed) | {former}) - {successor}

        store.save(team, dataclasses.replace(workspace, owner_id = successor, admins_allowed = tuple(sorted(allowed))), update_user = former)
        ack(response_action = 'clear')

        for user in [former, successor]: refresh(team, user)

        tell(successor, 'notice.ownership', owner = former, product = threadvault.product.NAME)
        tell(former, 'notice.ownership.done', user = successor, product = threadvault.product.NAME)

    application.use(threadvault.slack.permission.restrict(settings, store, frozenset({'owner', 'operator'})))
    application.event('app_home_opened')(publish)
    application.event('message')(note)
    application.action(threadvault.slack.view.CONNECTION_ACTION)(connect)
    application.action(threadvault.slack.view.DISCONNECTION_ACTION)(disconnect)
    application.action(threadvault.slack.view.INSTALLATION_ACTION)(install)
    application.action(threadvault.slack.view.LINK_ACTION)(follow)
    application.action(threadvault.slack.view.DESTINATION_ACTION)(offer)
    application.view(threadvault.slack.view.DESTINATION_CALLBACK)(submit)
    application.options(threadvault.slack.view.REPOSITORY_ACTION)(suggest)
    application.action(threadvault.slack.view.CREATION_ACTION)(propose)
    application.view(threadvault.slack.view.CREATION_CALLBACK)(create)
    application.action(threadvault.slack.view.BACKUP_ACTION)(launch)
    application.action(threadvault.slack.view.RESYNCHRONISATION_ACTION)(resynchronise)
    application.action(threadvault.slack.view.SETTINGS_ACTION)(configure)
    application.options(threadvault.slack.view.TIMEZONE_ACTION)(search)
    application.view(threadvault.slack.view.SETTINGS_CALLBACK)(adjust)
    application.action(threadvault.slack.view.PERMISSIONS_ACTION, middleware = guard)(manage)
    application.view(threadvault.slack.view.PERMISSIONS_CALLBACK, middleware = guard)(review)
    application.view(threadvault.slack.view.PERMISSIONS_CONFIRMATION, middleware = guard)(apply)
    application.action(threadvault.slack.view.TRANSFER_ACTION, middleware = guard)(cede)
    application.view(threadvault.slack.view.TRANSFER_CALLBACK, middleware = guard)(nominate)
    application.view(threadvault.slack.view.TRANSFER_CONFIRMATION, middleware = guard)(transfer)

    return schedule

def detach(
    function: collections.abc.Callable[[], None]
) -> None:

    """Runs a function in a daemon thread, so that a listener returns at once and the app stops without waiting for it.

    Args:
        function: The function.
    """

    threading.Thread(target = function, daemon = True).start()
