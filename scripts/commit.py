# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Checks that a commit message follows the conventions of this project."""

import argparse
import pathlib
import re
import sys
import typing

# Same as the type-enum rule of @commitlint/config-conventional:
# https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional
CATEGORIES = ('build', 'chore', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'revert', 'style', 'test')

# GitHub truncates longer subjects with an ellipsis.
SUBJECT_LENGTH_MAXIMUM = 72

# `git commit --verbose` writes the diff below this line; it is not part of the message.
LINE_SCISSORS = '# ------------------------ >8 ------------------------'
SUBJECT_PREFIXES = ('Merge ', 'Revert "', 'amend! ', 'fixup! ', 'squash! ')
SUBJECT_PATTERN = re.compile(r'(?P<type>\w+)(?P<scope>\([^)]*\))?!?: (?P<summary>\S.*)')
ARTICLE_PATTERN = re.compile(r'\b(?:a|an|the)\b', re.IGNORECASE)
TRAILER_PATTERN = re.compile(r'(?:Co-authored-by|Signed-off-by): \S.*', re.IGNORECASE)

def find(
    message: str
) -> list[str]:

    """Lists every convention that a commit message breaks.

    Args:
        message: Contents of the commit message file as Git wrote it,
                 including comment lines and any diff below the scissors line.

    Returns:
        One explanation for each broken convention;
        empty when the message is valid.
    """

    if not (lines := _extract(message)): return ['The commit message is empty']

    subject, *trailers = lines

    if subject.startswith(SUBJECT_PREFIXES): return []

    return [*_verify_subject(subject), *_verify_trailers(trailers)]

def main(
    arguments: list[str] | None = None
) -> int:

    """Checks the commit message file that pre-commit passes.

    Args:
        arguments: Command-line arguments without the program name.
                   When None, the arguments of the current process are used.

    Returns:
        The exit status of the command.

    Raises:
        SystemExit: argparse handled the arguments itself:
                    it printed help (status 0) or a usage error (status 2).
    """

    parser = argparse.ArgumentParser(description = 'Check a commit message against the project conventions.')
    parser.add_argument('message', type = pathlib.Path, help = 'file that holds the message')

    namespace = parser.parse_args(arguments)
    message = typing.cast(pathlib.Path, namespace.message).read_text(encoding = 'utf-8')

    for problem in (problems := find(message)): sys.stderr.write(f'{problem}\n')

    return 1 if problems else 0

def _extract(
    message: str
) -> list[str]:

    lines: list[str] = []

    for line in message.splitlines():

        if line == LINE_SCISSORS: break
        if not line.startswith('#'): lines.append(line.rstrip())

    while lines and not lines[0]: del lines[0]
    while lines and not lines[-1]: del lines[-1]

    return lines

def _verify_subject(
    subject: str
) -> list[str]:

    if (match := SUBJECT_PATTERN.fullmatch(subject)) is None: return ['Write the subject as "type: summary", such as "feat: add vault path layout"']

    category, scope, summary = match.group('type', 'scope', 'summary')
    problems: list[str] = []

    if len(subject) > SUBJECT_LENGTH_MAXIMUM: problems.append(f'Shorten the subject to {SUBJECT_LENGTH_MAXIMUM} characters or fewer')
    if category not in CATEGORIES: problems.append(f'Unknown type "{category}"; use {', '.join(CATEGORIES)}')
    if scope: problems.append(f'Remove the scope {scope}; scopes are not used')
    if summary[0].isupper(): problems.append('Start the summary with a lower-case letter')
    if (articles := ARTICLE_PATTERN.findall(summary)): problems.append(f'Remove the articles: {', '.join(articles)}')

    return problems

def _verify_trailers(
    lines: list[str]
) -> list[str]:

    if any(line and not TRAILER_PATTERN.fullmatch(line) for line in lines): return ['Remove the body; only Co-authored-by and Signed-off-by trailers may follow the subject']
    if lines and lines[0]: return ['Leave a blank line between the subject and the trailers']

    return []

if __name__ == '__main__':

    raise SystemExit(main())
