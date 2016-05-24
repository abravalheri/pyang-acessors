#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""
Tests for YANG modules without complex structures, just simple leafs
"""
from os.path import join

import pytest

from pyangext.utils import parse

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"


@pytest.fixture()
def list_example(ctx, module_dir):
    """YANG example with lists: 1 without key, 1 with key, 1 with >1 keys"""
    text = """
        module list-example {
            namespace "http://acme.example.com/system";
            prefix "aclist";

            organization "ACME Inc.";
            contact "joe@acme.example.com";
            description
                "The module for entities implementing the ACME system.";

            revision 2007-11-05 {
                description "Initial revision.";
            }

            list companies {
                leaf name { type string; }
            }

            list domains {
                key url;
                leaf url { type string; }
                leaf company { type string; }
            }

            list users {
                key "company login";
                leaf company { type string; }
                leaf login { type string; }
                leaf name { type string; }
                leaf surname { type string; }
            }

            leaf-list slogans { type string; }
        }
        """
    with open(join(module_dir, 'list-example.yang'), 'w') as fp:
        fp.write(text)

    module = parse(text, ctx)
    ctx.add_parsed_module(module)

    return module


@pytest.fixture
def rpc_module(generator, list_example):
    """Output from generator for the example module"""
    assert list_example
    return generator.transform(list_example)


def test_create_id_group_for_implicity_key(rpc_module):
    """
    should create a grouping named (list-item name + id-prefix)
    should have an ID leaf inside this group
    """
    id_group = rpc_module.find('grouping', 'default-identification')
    assert id_group
    assert id_group.find('leaf', 'id')


def test_id_group_include_explicity_keys(rpc_module):
    """
    should create a grouping named (list-item name + id-prefix)
    should have all the key leafs inside this group
    """
    id_group = rpc_module.find('grouping', 'domain-identification')
    assert id_group
    assert id_group.find('leaf', 'url')

    id_group = rpc_module.find('grouping', 'user-identification')
    assert id_group
    assert id_group.find('leaf', 'company')
    assert id_group.find('leaf', 'login')
