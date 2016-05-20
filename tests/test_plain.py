#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""
Tests for YANG modules without complex structures, just simple leafs
"""

from os.path import join

import pytest

from pyangext.syntax_tree import find

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"


@pytest.fixture()
def plain_example(ctx, parse):
    """Plain YANG example, just with leafs, no nested structures"""
    module = parse(
        """
        module plain-example {
            namespace "http://acme.example.com/system";
            prefix "acme";

            organization "ACME Inc.";
            contact "joe@acme.example.com";
            description
                "The module for entities implementing the ACME system.";

            revision 2007-11-05 {
                description "Initial revision.";
            }

            leaf host-name {
                type string;
                description "Hostname for this system";
            }

            leaf type {
                type string;
            }

            leaf state {
                type enumeration {
                    enum "off";
                    enum "active";
                    enum "idle";
                }
                config false;
            }
        }
        """
    )
    ctx.add_parsed_module(module)

    return module


@pytest.fixture
def rpc_module(generator, plain_example):
    """Output from generator for the example module"""
    assert plain_example
    return generator.transform(plain_example)


def test_generate_accessors(rpc_module):
    """
    the generated module should not have get accessors if leaf
        has no parameter
    The generated module should not have ``set`` accessors for
        ``config false`` leafs
    The generated module should have ``set`` accessors for leafs
        without ``config false``
    """
    print rpc_module.dump()
    for leaf_name in ('host-name', 'type', 'state'):
        assert not rpc_module.find('rpc', 'get-'+leaf_name)
        assert not rpc_module.find('grouping', 'get-'+leaf_name+'-request')
        assert not rpc_module.find('grouping', 'get-'+leaf_name+'-response')

    assert not rpc_module.find('rpc', 'set-state')
    assert not rpc_module.find('grouping', 'set-state-request')
    assert not rpc_module.find('grouping', 'set-state-response')

    for leaf_name in ('host-name', 'type'):
        assert rpc_module.find('rpc', 'set-'+leaf_name)
        assert rpc_module.find('grouping', 'set-'+leaf_name+'-request')
        assert rpc_module.find('grouping', 'set-'+leaf_name+'-response')


def test_leaf_definition_inside_groups(rpc_module):
    """
    each request/response grouping should have the leaf definition
       and an ``error`` field
    """
    for grouping in rpc_module.find('grouping'):
        parts = grouping.unwrap().arg.split('-')
        accessor = parts[0]
        leaf_name = '-'.join(parts[1:-1])
        moment = parts[-1]
        if accessor not in ('set', 'add'):
            assert grouping.find('leaf', leaf_name)
        if moment == 'response':
            assert grouping.find(arg='error')
