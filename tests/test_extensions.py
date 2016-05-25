#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""
Tests for YANG modules with extension
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

            import pyang-accessors { prefix accessor; }

            organization "ACME Inc.";
            contact "joe@acme.example.com";
            description
                "The module for entities implementing the ACME system.";

            revision 2007-11-05 {
                description "Initial revision.";
            }

            list companies {
                leaf name { type string; }
                leaf-list addresses {
                    type string;
                    accessor:modifier atomic;
                }
                accessor:modifier include;
            }

            list domains {
                key url;
                leaf url { type string; }
                leaf company { type string; }
                accessor:modifier include-item;
            }

            list users {
                key "company login";
                leaf company { type string; }
                leaf login { type string; }
                leaf name { type string; }
                leaf surname { type string; }
                leaf-list phone { type string; }
                accessor:modifier atomic-item;
            }

            container admin {
                leaf email { type string; }
                accessor:modifier atomic;
            }

            leaf-list rooms {
                type string;
                accessor:item-name "room-name";
            }
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


def test_leaf_list_unchanged_if_atomic(rpc_module):
    """
    should consider a leaf-list as a list if atomic
    should have no accessor for the items
    should have set + get for the collection
    """
    node = rpc_module.find('grouping', 'company-addresses-data')
    assert node
    assert not rpc_module.find('rpc', 'set-company-address')
    assert not rpc_module.find('rpc', 'get-company-address')
    assert not rpc_module.find('rpc', 'add-company-address')
    assert not rpc_module.find('rpc', 'remove-company-address')
    assert rpc_module.find('rpc', 'get-company-addresses')
    assert rpc_module.find('rpc', 'set-company-addresses')


def test_add_plural_if_include(rpc_module):
    """
    should insert a list node if include
    should have set + get for the collection
    """
    node = rpc_module.find('grouping', 'companies-data')
    assert node
    assert node.find('list', 'companies')
    assert rpc_module.find('rpc', 'get-companies')
    assert rpc_module.find('rpc', 'set-companies')


def test_add_singular_if_include_item(rpc_module):
    """
    should insert a item node if include item
    should have all accessors for the items
    should have not set + get for the collection
    should have accessors for child
    """
    node = rpc_module.find('grouping', 'domain-data')
    assert node
    assert rpc_module.find('rpc', 'set-domain')
    assert rpc_module.find('rpc', 'get-domain')
    assert rpc_module.find('rpc', 'add-domain')
    assert rpc_module.find('rpc', 'remove-domain')
    assert not rpc_module.find('rpc', 'get-domains')
    assert not rpc_module.find('rpc', 'set-domains')
    assert rpc_module.find('rpc', 'get-domain-company')
    assert rpc_module.find('rpc', 'set-domain-company')


def test_add_singular_if_atomic_item_but_not_child(rpc_module):
    """
    should insert a list item if atomic item but no child
    should have all accessors for the items
    should have not set + get for the collection
    should have no accessor for child
    """
    node = rpc_module.find('grouping', 'user-data')
    assert node
    assert not rpc_module.find('grouping', 'user-company-data')
    assert rpc_module.find('rpc', 'set-user')
    assert rpc_module.find('rpc', 'get-user')
    assert rpc_module.find('rpc', 'add-user')
    assert rpc_module.find('rpc', 'remove-user')
    assert not rpc_module.find('rpc', 'get-user-login')
    assert not rpc_module.find('rpc', 'set-user-login')


def test_atomic_for_container(rpc_module):
    """
    should insert operations for container, but no child
    """
    node = rpc_module.find('grouping', 'admin-data')
    assert node
    assert not rpc_module.find('grouping', 'admin-email-data')
    assert rpc_module.find('rpc', 'set-admin')
    assert rpc_module.find('rpc', 'get-admin')
    assert not rpc_module.find('rpc', 'get-admin-email')
    assert not rpc_module.find('rpc', 'set-admin-email')


def test_item_name_override_name(rpc_module):
    """
    should use the item-name
    should not use the argument
    """
    assert rpc_module.find('grouping', 'room-name-response')
    assert rpc_module.find('rpc', 'set-room-name')
    assert rpc_module.find('rpc', 'get-room-name')
    assert not rpc_module.find('grouping', 'room-response')
    assert not rpc_module.find('rpc', 'get-room')
    assert not rpc_module.find('rpc', 'set-room')
