import cryptography.fernet
import pytest

import threadvault.product
import threadvault.terminal

def test_terminal_version(
    capsys: pytest.CaptureFixture[str]
) -> None:

    expected = f'{threadvault.product.COMMAND} {threadvault.product.VERSION}'

    with pytest.raises(SystemExit) as exception: threadvault.terminal.main(['--version'])

    assert exception.value.code == 0
    assert capsys.readouterr().out.strip() == expected

def test_terminal_missing(
    capsys: pytest.CaptureFixture[str]
) -> None:

    with pytest.raises(SystemExit) as exception: threadvault.terminal.main([])

    assert exception.value.code == 2
    assert 'required: <command>' in capsys.readouterr().err

def test_terminal_command_generate_key(
    capsys: pytest.CaptureFixture[str]
) -> None:

    assert threadvault.terminal.main(['generate-key']) == 0

    cryptography.fernet.Fernet(capsys.readouterr().out.strip())
