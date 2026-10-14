# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import datetime
import typing

import pytest

import threadvault.backup.fetch

NOW = datetime.datetime.fromtimestamp(1000000000, datetime.UTC)

THREADS_CHANGED = [
    ([{'ts': '100.0', 'reply_count': 1, 'latest_reply': '200.0'}], [], ['100.0']),
    ([{'ts': '100.0', 'reply_count': 1, 'latest_reply': '200.0'}], [{'ts': '100.0', 'reply_count': 1, 'latest_reply': '200.0'}], []),
    ([{'ts': '100.0', 'reply_count': 1, 'latest_reply': '300.0'}], [{'ts': '100.0', 'reply_count': 1, 'latest_reply': '200.0'}], ['100.0']),
    ([{'ts': '100.0', 'reply_count': 1, 'latest_reply': '200.0'}], [{'ts': '100.0', 'reply_count': 2, 'latest_reply': '200.0'}], ['100.0']),
    ([{'ts': '100.0'}], [], []),
    ([{'ts': '300.0', 'reply_count': 1, 'latest_reply': '400.0'}, {'ts': '100.0', 'reply_count': 1, 'latest_reply': '200.0'}], [], ['100.0', '300.0'])
]

def test_fetch_window_lookback() -> None:

    assert threadvault.backup.fetch.window(NOW, 1) == ('999913600.000000', '1000000000.000000')

def test_fetch_window_whole() -> None:

    assert threadvault.backup.fetch.window(NOW, None) == ('0', '1000000000.000000')

@pytest.mark.parametrize(('history', 'stored', 'expected'), THREADS_CHANGED)
def test_fetch_message_change(
    history: list[dict[str, typing.Any]],
    stored: list[dict[str, typing.Any]],
    expected: list[str]
) -> None:

    assert threadvault.backup.fetch.threads(history, stored) == expected

def test_fetch_thread_mark() -> None:

    assert threadvault.backup.fetch.threads([{'ts': '300.0', 'reply_count': 1, 'latest_reply': '400.0'}], [], ['300.0', '100.0']) == ['100.0', '300.0']

def test_fetch_day_mark() -> None:

    assert threadvault.backup.fetch.days([datetime.date(2001, 9, 9), datetime.date(2001, 9, 7), datetime.date(2001, 9, 8), datetime.date(2001, 9, 6)], '999907200.000000') == [('999734400.000000', '999820800.000000'), ('999820800.000000', '999907200.000000')]
