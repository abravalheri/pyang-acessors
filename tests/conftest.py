#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""
    Dummy conftest.py for pyang_accessors.

    If you don't know what this is for, just leave it empty.
    Read more about conftest.py under:
    https://pytest.org/latest/plugins.html
"""
from __future__ import absolute_import, division, print_function

import pytest

from pyang.yang_parser import YangParser
from pyangext.utils import create_context

from pyang_accessors.generators import RPCGenerator


@pytest.fixture(scope='session')
def module_dir(tmpdir_factory):
    """file repository for tests"""
    return str(tmpdir_factory.mktemp('fixtures'))


@pytest.fixture(scope='function')
def ctx(module_dir):
    """``pyang.Context`` with examples repository"""
    return create_context(module_dir)


@pytest.fixture
def generator(ctx):
    """Pre-instantiated Accessor Generator"""
    return RPCGenerator(ctx)


@pytest.fixture
def parse(ctx):
    """YANG Parser with no overhead"""
    parser = YangParser()

    def _parse(text):
        return parser.parse(ctx, 'pytest-test', text)

    return _parse
