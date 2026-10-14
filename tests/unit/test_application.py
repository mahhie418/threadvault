# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import pathlib

import pytest

import threadvault.slack.application

def test_application_lock_exclusion(
    tmp_path: pathlib.Path
) -> None:

    with threadvault.slack.application.lock(tmp_path), pytest.raises(threadvault.slack.application.LockError, match = 'already running'), threadvault.slack.application.lock(tmp_path): pass
    with threadvault.slack.application.lock(tmp_path): pass
