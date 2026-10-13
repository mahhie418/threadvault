"""Workspace data in the JSON format of Slack's own export."""

import collections
import collections.abc
import datetime
import decimal
import json
import operator
import os
import pathlib
import typing

RAW_DIRECTORY = 'raw'

USERS_FILE = 'users.json'
CHANNELS_FILE = 'channels.json'
GROUPS_FILE = 'groups.json'

_FIELDS_USER_EXCLUDED = frozenset({'tz_label', 'tz_offset', 'updated'})
_FIELDS_PROFILE_EXCLUDED = frozenset({'huddle_state', 'huddle_state_expiration_ts', 'status_emoji', 'status_emoji_display_info', 'status_expiration', 'status_text', 'status_text_canonical'})
_FIELDS_CHANNEL_INCLUDED = frozenset({'created', 'creator', 'id', 'is_archived', 'is_general', 'name', 'purpose', 'topic'})

_FIELDS_MESSAGE_STATE_EXCLUDED = frozenset({'last_read', 'subscribed'})
_FIELDS_MESSAGE_PROFILE_INCLUDED = frozenset({'avatar_hash', 'display_name', 'first_name', 'image_72', 'is_restricted', 'is_ultra_restricted', 'name', 'real_name', 'team'})

def users(
    directory: pathlib.Path,
    users: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]]
) -> None:

    """Writes users.json with every user, as Slack's export does.

    Fields that change by themselves, such as the status, are left out.

    Args:
        directory: Directory of the raw data in the vault.
        users: Users as users.list returns them.
    """

    entries = [_filter(user, _FIELDS_USER_EXCLUDED, action = 'exclude') | {'profile': _filter(user.get('profile', {}), _FIELDS_PROFILE_EXCLUDED, action = 'exclude')} for user in sorted(users, key = operator.itemgetter('id'))]

    _write(pathlib.Path(os.path.join(directory, USERS_FILE)), entries)

def channels(
    directory: pathlib.Path,
    channels: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    members: collections.abc.Mapping[str, collections.abc.Iterable[str]]
) -> None:

    """Writes the public channels to channels.json and the private ones to groups.json.

    Each channel keeps the fields that Slack's export writes, with its members.

    Args:
        directory: Directory of the raw data in the vault.
        channels: Channels as conversations.list returns them.
        members: User IDs of the members by channel ID.
    """

    entries = [(channel.get('is_private', False), _filter(channel, _FIELDS_CHANNEL_INCLUDED, action = 'include') | {'members': sorted(members.get(channel['id'], ()))}) for channel in sorted(channels, key = operator.itemgetter('id'))]

    _write(pathlib.Path(os.path.join(directory, CHANNELS_FILE)), [entry for private, entry in entries if not private])
    _write(pathlib.Path(os.path.join(directory, GROUPS_FILE)), [entry for private, entry in entries if private])

def messages(
    directory: pathlib.Path,
    messages: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]],
    users: collections.abc.Iterable[collections.abc.Mapping[str, typing.Any]]
) -> None:

    """Writes the messages of a channel to one file a day, as Slack's export does.

    A message goes to the file of the UTC date of its timestamp, so a thread
    reply sits in the file of the day it was posted. Each file holds the given
    messages of its day in order of time and replaces the file that was there,
    and the file of a day without messages is removed, so give every message
    of the channel. A message of a known user gets the user_profile of Slack's
    export. Fields that describe the reader are left out.

    Args:
        directory: Directory of the channel in the raw data.
        messages: Messages of the channel, each once, as conversations.history
                  and conversations.replies return them.
        users: Users as users.list returns them.
    """

    profiles = {user['id']: _profile(user) for user in users}
    days: dict[str, list[dict[str, typing.Any]]] = collections.defaultdict(list)

    for message in sorted(messages, key = lambda message: decimal.Decimal(message['ts'])):

        entry = _filter(message, _FIELDS_MESSAGE_STATE_EXCLUDED, action = 'exclude')
        day = datetime.datetime.fromtimestamp(float(message['ts']), datetime.UTC).date().isoformat()

        if message.get('user') in profiles: entry['user_profile'] = profiles[message['user']]

        days[day].append(entry)

    directory.mkdir(exist_ok = True)

    for day, entries in days.items(): _write(pathlib.Path(os.path.join(directory, f'{day}.json')), entries)

    stale = [path for path in directory.glob('*.json') if path.stem not in days]

    for path in stale: path.unlink()

def _filter(
    mapping: collections.abc.Mapping[str, typing.Any],
    keys: collections.abc.Set[str],
    *,
    action: typing.Literal['include', 'exclude']
) -> dict[str, typing.Any]:

    return {key: value for key, value in mapping.items() if (key in keys) == (action == 'include')}

def _profile(
    user: collections.abc.Mapping[str, typing.Any]
) -> dict[str, typing.Any]:

    return _filter({**user, **user.get('profile', {})}, _FIELDS_MESSAGE_PROFILE_INCLUDED, action = 'include')

def _write(
    path: pathlib.Path,
    document: object
) -> None:

    text = json.dumps(document, ensure_ascii = False, indent = 2, sort_keys = True)
    temporary = path.with_name(f'{path.name}.tmp')

    try:

        temporary.write_text(f'{text}\n', encoding = 'utf-8', newline = '\n')
        temporary.replace(path)

    finally:

        temporary.unlink(missing_ok = True)
