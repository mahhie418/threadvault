import threadvault.vault.merge

def create(
    ts: str,
    thread_ts: str | None = None,
    text: str = 'xxx'
) -> dict[str, str]:

    message = {'text': text, 'ts': ts}

    if thread_ts is not None: message['thread_ts'] = thread_ts

    return message

def merge(
    stored: list[dict[str, str]],
    history: list[dict[str, str]],
    threads: dict[str, list[dict[str, str]]]
) -> tuple[list[str], list[str]]:

    outcome = threadvault.vault.merge.merge(stored, history, threads, oldest = '400.0', latest = '600.0')

    return [message['ts'] for message in outcome.messages], [message['ts'] for message in outcome.deleted]

def test_merge_message_history_added() -> None:

    assert merge([create('100.0')], [create('500.0'), create('400.0')], {}) == (['100.0', '400.0', '500.0'], [])

def test_merge_message_history_edited() -> None:

    outcome = threadvault.vault.merge.merge([create('400.0', text = 'xxx1')], [create('400.0', text = 'xxx2')], {}, oldest = '400.0', latest = '600.0')

    assert outcome.messages == [create('400.0', text = 'xxx2')]
    assert outcome.deleted == []

def test_merge_message_history_deleted() -> None:

    assert merge([create('400.0'), create('500.0'), create('600.0')], [create('500.0')], {}) == (['500.0'], ['400.0', '600.0'])

def test_merge_unknown_window_exceeded() -> None:

    assert merge([create('100.0'), create('700.0')], [], {}) == (['100.0', '700.0'], [])

def test_merge_unknown_thread_unfetched() -> None:

    assert merge([create('100.0', '100.0'), create('400.0', '100.0')], [], {}) == (['100.0', '400.0'], [])

def test_merge_unknown_history_edited() -> None:

    stored = [create('100.0', '100.0'), create('400.0', '100.0', 'xxx1')]
    outcome = threadvault.vault.merge.merge(stored, [create('400.0', '100.0', 'xxx2')], {}, oldest = '400.0', latest = '600.0')

    assert outcome.messages == [create('100.0', '100.0'), create('400.0', '100.0', 'xxx2')]
    assert outcome.deleted == []

def test_merge_thread_reply_replaced() -> None:

    stored = [create('100.0', '100.0'), create('400.0', '100.0'), create('500.0', '100.0')]
    threads = {'100.0': [create('100.0', '100.0'), create('400.0', '100.0'), create('600.0', '100.0')]}

    assert merge(stored, [], threads) == (['100.0', '400.0', '600.0'], ['500.0'])

def test_merge_thread_window_exceeded() -> None:

    stored = [create('100.0', '100.0'), create('200.0', '100.0'), create('300.0', '100.0')]
    threads = {'100.0': [create('100.0', '100.0'), create('300.0', '100.0')]}

    assert merge(stored, [], threads) == (['100.0', '300.0'], ['200.0'])
