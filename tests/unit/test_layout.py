import unicodedata

import pytest

import threadvault.vault.layout

NAMES_RESERVED = ['aux', 'CON', 'nul', 'Prn', 'com1', 'COM9', 'lpt¹']

NAMES_CORRESPONDENCE = [
    ('xxx-xxx_xxx', 'xxx-xxx_xxx'),
    ('データ', 'データ'),
    (unicodedata.normalize('NFD', 'データ'), 'データ'),
    ('xxx"*./:<>?\\|xxx', 'xxx__________xxx'),
    ('xxx\x00\x1f\x7f\ud800xxx', 'xxx____xxx'),
    ('xxx xxx\u3000xxx\txxx', 'xxx_xxx_xxx_xxx'),
    ('xxx.', 'xxx_'),
    ('あ' * threadvault.vault.layout.NAME_SIZE_MAXIMUM, 'あ' * (threadvault.vault.layout.NAME_SIZE_MAXIMUM // 3))
]

DIRECTORIES_UPDATED = [
    ({'CXXX1': 'xxx'}, {'CXXX1': 'xxx'}, {'CXXX1': 'xxx'}),
    ({'CXXX1': 'xxx'}, {'CXXX1': 'xxx-CXXX1'}, {'CXXX1': 'xxx-CXXX1'}),
    ({'CXXX1': 'xxx_xxx'}, {'CXXX1': 'xxx'}, {'CXXX1': 'xxx_xxx'}),
    ({'CXXX1': 'xxx', 'CXXX2': 'XXX'}, {'CXXX1': 'xxx'}, {'CXXX1': 'xxx', 'CXXX2': 'XXX-CXXX2'}),
    ({'CXXX2': 'xxx'}, {'CXXX1': 'xxx'}, {'CXXX1': 'xxx', 'CXXX2': 'xxx-CXXX2'}),
    ({'CXXX1': 'xxx_xxx', 'CXXX2': 'xxx'}, {'CXXX1': 'xxx', 'CXXX2': 'xxx_xxx'}, {'CXXX1': 'xxx_xxx', 'CXXX2': 'xxx'}),
    ({'CXXX1': 'xxx-cxxx2', 'CXXX2': 'xxx', 'CXXX3': 'XXX'}, {'CXXX1': 'xxx-cxxx2'}, {'CXXX1': 'xxx-cxxx2', 'CXXX2': 'xxx-CXXX2-CXXX2', 'CXXX3': 'XXX-CXXX3'})
]

@pytest.mark.parametrize(('name', 'expected'), NAMES_CORRESPONDENCE)
def test_layout_name_sanitisation(
    name: str,
    expected: str
) -> None:

    assert threadvault.vault.layout.assign({'CXXX': name}, {}) == {'CXXX': expected}

@pytest.mark.parametrize('name', NAMES_RESERVED)
def test_layout_name_reservation(
    name: str
) -> None:

    assert threadvault.vault.layout.assign({'CXXX': name}, {}) == {'CXXX': f'{name}-CXXX'}

def test_layout_name_empty() -> None:

    assert threadvault.vault.layout.assign({'CXXX': ''}, {}) == {'CXXX': 'CXXX'}

def test_layout_name_confliction() -> None:

    channels = {'CXXX1': 'xxx', 'CXXX2': 'XXX', 'CXXX3': 'xxx-cxxx1', 'CXXX4': 'xxx-xxx'}
    expected = {'CXXX1': 'xxx-CXXX1', 'CXXX2': 'XXX-CXXX2', 'CXXX3': 'xxx-cxxx1-CXXX3', 'CXXX4': 'xxx-xxx'}

    assert threadvault.vault.layout.assign(channels, {}) == expected

@pytest.mark.parametrize(('channels', 'directories', 'expected'), DIRECTORIES_UPDATED)
def test_layout_name_update(
    channels: dict[str, str],
    directories: dict[str, str],
    expected: dict[str, str]
) -> None:

    assert threadvault.vault.layout.assign(channels, directories) == expected
