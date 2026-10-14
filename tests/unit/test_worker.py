# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import pytest

import threadvault.worker

def test_worker_backup_start() -> None:

    events = []
    worker = threadvault.worker.Worker(lambda function: function())

    assert worker.start(lambda: events.append(('backup', worker.busy())), lambda: events.append(('finish', worker.busy())))
    assert events == [('backup', True), ('finish', False)]
    assert not worker.busy()

def test_worker_backup_exclusivity() -> None:

    events, pending = [], []
    worker = threadvault.worker.Worker(pending.append)

    assert worker.start(lambda: events.append('xxx1'), lambda: None)
    assert worker.busy()
    assert not worker.start(lambda: events.append('xxx2'), lambda: None)

    pending.pop()()

    assert not worker.busy()
    assert worker.start(lambda: events.append('xxx3'), lambda: None)

    pending.pop()()

    assert events == ['xxx1', 'xxx3']

def test_worker_backup_failure() -> None:

    events = []
    worker = threadvault.worker.Worker(lambda function: function())

    def fail() -> None:

        raise RuntimeError('xxx')

    with pytest.raises(RuntimeError, match = 'xxx'): worker.start(fail, lambda: events.append(worker.busy()))

    assert events == [False]
    assert not worker.busy()
