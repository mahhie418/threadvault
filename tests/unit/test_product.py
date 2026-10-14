# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import os
import pathlib
import tomllib

import threadvault.product

PYPROJECT = pathlib.Path(os.path.join(pathlib.Path(__file__).parents[2], 'pyproject.toml'))
CONTENT = tomllib.loads(PYPROJECT.read_text(encoding = 'utf-8'))['project']

def test_product_pyproject() -> None:

    assert CONTENT['name'] == threadvault.product.NAME
    assert CONTENT['description'] == threadvault.product.SUMMARY
    assert CONTENT['version'] == threadvault.product.VERSION
    assert threadvault.product.COMMAND in CONTENT['scripts']
