#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""
Tests for YANG modules without complex structures, just simple leafs
"""
import pytest

from pyangext.utils import dump, parse

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"


@pytest.fixture()
def plain_example(ctx):
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

            typedef state-type {
                type enumeration {
                    enum "off";
                    enum "active";
                    enum "idle";
                }
            }

            leaf host-name {
                type string;
                description "Hostname for this system";
            }

            leaf type {
                type string;
            }

            leaf state {
                type state-type;
                config false;
            }

            leaf-list admins {
                type string;
                config false;
            }

            leaf-list users {
                type string;
            }
        }
        """,
        ctx
    )
    ctx.add_parsed_module(module)

    return module


@pytest.fixture
def rpc_module(generator, plain_example):
    """Output from generator for the example module"""
    assert plain_example
    return generator.transform(plain_example)


def test_generate_get_accessors(rpc_module):
    """
    all entry-points should have READ accessors
    If the entry-point has no key, its request will not have parameters
    """
    for leaf_name in ('host-name', 'type', 'state'):
        rpc = rpc_module.find('rpc', 'get-'+leaf_name)
        assert rpc
        assert not rpc.find('input')


def test_consider_leaf_list_atomic_item(rpc_module):
    """
    leaf-lists should be considered atomic-item
    """
    # entry point receives name in singular
    for leaf_name in ('admin', 'user'):
        rpc = rpc_module.find('rpc', 'get-'+leaf_name)
        assert rpc
        # get needs an ID to find the correct entry
        input_ = rpc.find('input')[0]
        assert input_.find('uses', leaf_name+'-id')


def test_generate_failure_condition(rpc_module):
    """
    all rpc outputs should have a response choice whith a failure case
    the failure case should have a ``uses failure`` statement
    """
    for rpc in rpc_module.find('rpc'):
        print rpc.dump()
        print '\n'.join([dump(x) for x in rpc.unwrap().i_children])
        choice = rpc.walk(
            lambda x: x.keyword == 'choice' and x.arg == 'response',
            key='i_children')
        assert choice
        assert choice.walk(
            lambda x: x.keyword == 'uses' and x.arg == 'failure')


def test_not_generate_set_for_config_false(rpc_module):
    """
    should not generate set accessors for ``config false`` nodes
    """
    for rpc_name in ('set-state', 'set-admin'):
        assert not rpc_module.find('rpc', rpc_name)


def test_generate_set_for_config_not_false(rpc_module):
    """
    should generate set accessors for leafs without ``config false``
    """
    for rpc_name in ('set-type', 'set-host-name', 'set-user'):
        assert rpc_module.find('rpc', rpc_name)


def test_generate_add_remove_for_lists_config_not_false(rpc_module):
    """
    should generate set accessors for leafs without ``config false``
    """
    for rpc_name in ('add-user', 'remove-user'):
        assert rpc_module.find('rpc', rpc_name)


def test_not_generate_add_remove_for_lists_config_false(rpc_module):
    """
    should generate set accessors for leafs without ``config false``
    """
    for rpc_name in ('add-admin', 'remove-admin'):
        assert not rpc_module.find('rpc', rpc_name)


@pytest.mark.skip(reason="TODO: not implemented yet")
def test_typedef_reference(rpc_module):
    """
    should not include typedef
    should referece typedef, using as prefix, the desired prefix in
        original module
    """
    yang = rpc_module.dump()
    assert 'typedef state-type' not in yang
    assert 'type acme:state-type;' in yang


def test_valid_yang(rpc_module):
    """
    module produced by transformation should be valid
    """
    assert rpc_module.validate()
    assert hasattr(rpc_module, 'i_children')
    assert rpc_module.i_children
