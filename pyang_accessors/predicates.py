# -*- coding: utf-8 -*-
"""Functions for qualifying nodes."""

from pyangext.definitions import DATA_STATEMENTS
from pyangext.utils import find

from .definitions import (
    ATOMIC,
    ATOMIC_ITEM,
    INCLUDE,
    INCLUDE_ITEM,
    MODIFIER_EXT,
)

__author__ = "Anderson Bravalheri"
__copyright__ = "Copyright (C) 2016 Anderson Bravalheri"
__license__ = "mozilla"


def is_atomic(statement):
    return (
        statement.keyword in ('leaf', 'anyxml') or
        find(statement, MODIFIER_EXT, ATOMIC, ignore_prefix=True)
    )


def is_atomic_item(statement):
    return (
        statement.keyword == 'leaf-list' or
        find(statement, MODIFIER_EXT, ATOMIC_ITEM, ignore_prefix=True)
    )


def is_data(statement):
    return statement.keyword in DATA_STATEMENTS


def is_included(statement):
    return find(statement, MODIFIER_EXT, INCLUDE, ignore_prefix=True)


def is_included_item(statement):
    return find(statement, MODIFIER_EXT, INCLUDE_ITEM, ignore_prefix=True)


def is_list(statement):
    return statement.keyword in ('list', 'leaf-list')


def is_read_only(statement):
    config = statement.search_one('config')
    return config and ('false' in config.arg)


def is_top_level(statement):
    return statement.keyword in ('module', 'submodule')