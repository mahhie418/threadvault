import os
import pathlib

import pytest

import commit

TRAILER = 'Co-Authored-By: xxx <xxx@xxx.xxx>'

VERBOSE = (
    'feat: xxx\n'
    '\n'
    '# Please enter the commit message for your changes.\n'
    '# ------------------------ >8 ------------------------\n'
    '# Do not modify or remove the line above.\n'
    'diff --git a/README.md b/README.md\n'
    '+The vault keeps a copy of the workspace.\n'
)

MESSAGES_VALID = [
    'feat: xxx\n', 'feat!: xxx\n', f'feat: xxx\n\n{TRAILER}\n',
    f'{'feat: ' + 'x' * (commit.SUBJECT_LENGTH_MAXIMUM - len('feat: '))}\n',
    'feat: xxxthe axxx\n', 'feat: xxx\n# xxx\n', VERBOSE,
    'Merge xxx\n', 'Revert "xxx"\n',
    'fixup! xxx\n', 'squash! xxx\n', 'amend! xxx\n',
]

MESSAGES_INVALID = [
    ('xxx\n', '"type: summary"'),
    ('feature: xxx\n', 'Unknown type "feature"'),
    ('feat(xxx): xxx\n', 'Remove the scope (xxx)'),
    ('feat: xxx the xxx\n', 'Remove the articles: the'),
    ('feat: An xxx\n', 'Remove the articles: An'),
    ('feat: xxx a xxx the xxx\n', 'Remove the articles: a, the'),
    ('feat: XXX\n', 'lower-case letter'),
    (f'{'feat: ' + 'x' * (commit.SUBJECT_LENGTH_MAXIMUM - len('feat: '))}xxx\n', 'Shorten the subject'),
    ('feat: xxx\n\nxxx\n', 'Remove the body'),
    (f'feat: xxx\n{TRAILER}\n', 'Leave a blank line'),
    ('# xxx\n', 'empty'),
]

@pytest.mark.parametrize('message', MESSAGES_VALID)
def test_commit_messages_valid(message: str) -> None:

    assert commit.find(message) == []

@pytest.mark.parametrize(('message', 'expected'), MESSAGES_INVALID)
def test_commit_messages_invalid(message: str, expected: str) -> None:

    problems = commit.find(message)

    assert any(expected in problem for problem in problems)

def test_commit_error_report() -> None:

    subject = 'feature(xxx): The ' + 'x' * commit.SUBJECT_LENGTH_MAXIMUM
    problems = commit.find(f'{subject}\n\nx\n')

    assert len(problems) == 6

def test_commit_hook_message_valid(
    tmp_path: pathlib.Path
) -> None:

    file = pathlib.Path(os.path.join(tmp_path, 'COMMIT_EDITMSG'))
    file.write_text(f'feat: xxx\n\n{TRAILER}\n', encoding = 'utf-8')

    assert commit.main([str(file)]) == 0

def test_commit_hook_message_invalid(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str]
) -> None:

    file = pathlib.Path(os.path.join(tmp_path, 'COMMIT_EDITMSG'))
    file.write_text(f'feat(xxx): xxx\n\n{TRAILER}\n', encoding = 'utf-8')

    assert commit.main([str(file)]) == 1
    assert 'Remove the scope (xxx)' in capsys.readouterr().err

def test_commit_hook_argparse(
    capsys: pytest.CaptureFixture[str]
) -> None:

    with pytest.raises(SystemExit) as exception: commit.main([])

    assert exception.value.code == 2
    assert 'required: message' in capsys.readouterr().err
