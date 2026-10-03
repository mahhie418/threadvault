"""Workspace data in the JSON format of Slack's own export."""

import collections.abc
import json
import operator
import os
import pathlib
import typing

USERS_FILE = 'users.json'
CHANNELS_FILE = 'channels.json'
GROUPS_FILE = 'groups.json'

_FIELDS_USER_EXCLUDED = frozenset({'tz_label', 'tz_offset', 'updated'})
_FIELDS_PROFILE_EXCLUDED = frozenset({'huddle_state', 'huddle_state_expiration_ts', 'status_emoji', 'status_emoji_display_info', 'status_expiration', 'status_text', 'status_text_canonical'})
_FIELDS_CHANNEL_INCLUDED = frozenset({'created', 'creator', 'id', 'is_archived', 'is_general', 'name', 'purpose', 'topic'})

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

def _filter(
    mapping: collections.abc.Mapping[str, typing.Any],
    keys: collections.abc.Set[str],
    *,
    action: typing.Literal['include', 'exclude']
) -> dict[str, typing.Any]:

    return {key: value for key, value in mapping.items() if (key in keys) == (action == 'include')}

def _write(
    path: pathlib.Path,
    document: object
) -> None:

    text = json.dumps(document, ensure_ascii = False, indent = 2, sort_keys = True)

    path.write_text(f'{text}\n', encoding = 'utf-8', newline = '\n')
