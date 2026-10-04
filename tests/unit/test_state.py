import json
import os
import pathlib

import pytest

import threadvault.vault.state

DIRECTORIES = {'CXXX2': 'テスト', 'CXXX1': 'xxx'}

STATES_INVALID = [
    ('xxx', 'not valid JSON'),
    ('[]', 'not a state file'),
    ('{"format_version": 1}', 'not a state file'),
    ('{"format_version": 0, "directories": {}}', 'not a state file'),
    ('{"format_version": 1, "directories": {"CXXX": 1}}', 'not a state file'),
    (json.dumps({'format_version': threadvault.vault.state.FORMAT_VERSION + 1, 'directories': {}}), 'newer version')
]

def locate(
    vault: pathlib.Path
) -> pathlib.Path:

    return pathlib.Path(os.path.join(vault, threadvault.vault.state.STATE_DIRECTORY, threadvault.vault.state.STATE_FILE))

def test_state_data_empty(
    tmp_path: pathlib.Path
) -> None:

    assert threadvault.vault.state.load(tmp_path) == {}

def test_state_data_consistency(
    tmp_path: pathlib.Path
) -> None:

    threadvault.vault.state.save(tmp_path, DIRECTORIES)

    assert threadvault.vault.state.load(tmp_path) == DIRECTORIES

def test_state_data_override(
    tmp_path: pathlib.Path
) -> None:

    threadvault.vault.state.save(tmp_path, DIRECTORIES)
    threadvault.vault.state.save(tmp_path, {'CXXX3': 'xxx'})

    assert threadvault.vault.state.load(tmp_path) == {'CXXX3': 'xxx'}

def test_state_data_format(
    tmp_path: pathlib.Path
) -> None:

    threadvault.vault.state.save(tmp_path, DIRECTORIES)

    file = locate(tmp_path)
    expected = '{\n  "directories": {\n    "CXXX1": "xxx",\n    "CXXX2": "テスト"\n  },\n  "format_version": 1\n}\n'

    assert file.read_bytes() == expected.encode('utf-8')
    assert [entry.name for entry in file.parent.iterdir()] == [threadvault.vault.state.STATE_FILE]

@pytest.mark.parametrize(('text', 'message'), STATES_INVALID)
def test_state_data_corruption(
    tmp_path: pathlib.Path,
    text: str,
    message: str
) -> None:

    file = locate(tmp_path)
    file.parent.mkdir()
    file.write_text(text, encoding = 'utf-8')

    with pytest.raises(threadvault.vault.state.StateError, match = message): threadvault.vault.state.load(tmp_path)
