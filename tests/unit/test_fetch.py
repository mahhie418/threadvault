import datetime
import typing

import pytest

import threadvault.backup.fetch

NOW = datetime.datetime.fromtimestamp(1000000000, datetime.UTC)

THREADS_CHANGED: list[tuple[list[dict[str, typing.Any]], list[dict[str, typing.Any]], list[str]]] = [
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
