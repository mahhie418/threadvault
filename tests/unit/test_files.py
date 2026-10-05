import unicodedata

import pytest

import threadvault.vault.files

FILE_TEST = {'created': 1698795000, 'id': 'FXXX1', 'mode': 'hosted', 'name': 'xxx.txt', 'url_private_download': 'https://files.slack.com/xxx'}

FILES_EXCLUDED = [
    {'id': 'FXXX2', 'mode': 'hidden_by_limit'},
    {'id': 'FXXX3', 'mode': 'tombstone'},
    {'id': 'FXXX4', 'mode': 'external', 'url_private_download': 'https://xxx.xxx/'},
    {'id': 'FXXX5', 'mode': 'hosted'}
]

NAMES_SANITISED = [
    ('xxx.txt', 'xxx.txt'),
    ('xxx:xxx?.txt', 'xxx_xxx_.txt'),
    ('xxx. .', 'xxx'),
    ('con.txt', '_con.txt'),
    (unicodedata.normalize('NFD', 'データ.txt'), 'データ.txt'),
    ('x' * 300 + '.txt', 'x' * 196 + '.txt'),
    ('', 'FXXX1')
]

def test_files_file_selection() -> None:

    assert threadvault.vault.files.select([{'files': [FILE_TEST, *FILES_EXCLUDED]}, {'files': [FILE_TEST]}, {'text': 'xxx'}]) == [FILE_TEST]

@pytest.mark.parametrize(('name', 'expected'), NAMES_SANITISED)
def test_files_name_sanitisation(
    name: str,
    expected: str
) -> None:

    assert threadvault.vault.files.locate(FILE_TEST | {'name': name}) == f'attachments/2023-10/FXXX1/{expected}'
