# -*- coding: utf-8 -*-
"""
"""
from collections import namedtuple
from itertools import chain as concat

from inflection import singularize

from pyangext.syntax_tree import StatementWrapper, find, select, dump

from pyang_accessors import __version__  # noqa
from pyang_accessors.definitions import (  # constants and identifiers
    CHANGE_OP,
    ITEM_ADD_OP,
    ITEM_REMOVE_OP,
    READ_OP,
)
from pyang_accessors.predicates import (
    is_atomic,
    is_atomic_item,
    is_data,
    is_included,
    is_included_item,
    is_list,
    is_read_only,
    is_top_level,
)

# create a uniq object for comparisson
_PRUNE = GeneratorExit()

READ_ONLY_OPS = [READ_OP]
DEFAULT_OPS = READ_ONLY_OPS + [CHANGE_OP]
DEFAULT_ITEM_OPS = DEFAULT_OPS + [ITEM_ADD_OP, ITEM_REMOVE_OP]


def ensure_validated(statement):
    if not (hasattr(statement, 'i_is_validated')
            and statement.i_is_validated):
        raise AttributeError(
            'Invalid module %s. Was the module validated?', statement.arg)


def find_keys(statement):
    key = statement.search_one('key')

    return key and [
        select(statement.i_children, arg=name)[0]
        for name in key.arg.split(' ')
    ]


def find_item_name(statement):
    # should not include name of the list, use instead the name
    # of the item
    item_name = find(statement, 'item-name')
    if item_name:
        return item_name[0].arg

    return singularize(statement.arg)


class EntryPoint(object):
    """Store information about an entry-point.

    An entry point is a node in the data tree that can be
    accessed/manipulated.

    Attributes:
        path (list): names of nodes the tree, ordered from root to target
        operations (list): list with names of operations.
            See :module:`pyang_accessors.definitions`
        payload (pyang.statements.Statement):
            statement that define the data node
        parent_keys (list): If any parent of the target link is an element
            of a list, its key is added to this list
        own_keys: list of keys for the target node
    """

    def __init__(self, path,
                 payload=None, operations=None,
                 parent_keys=None, own_keys=None):
        """Normalize input data (add defaults)"""
        if operations is None:
            operations = [READ_OP]
        if parent_keys is None:
            parent_keys = []
        if own_keys is None:
            own_keys = []

        self.path = path
        self.payload = payload
        self.operations = operations
        self.parent_keys = parent_keys
        self.own_keys = own_keys

    def copy(self):
        """Copy the entry-point avoiding overriding it."""

        payload = self.payload and (
            self.payload.unwrap().copy()
            if isinstance(self.payload, StatementWrapper)
            else self.payload.copy()
        )

        return type(self)(
            self.path,
            payload,
            self.operations[:],
            self.parent_keys[:],
            self.own_keys[:])


class DataScanner(object):
    def __init__(self, builder, key_template,
                 name_composer, value_arg='value'):
        self.key_template = key_template
        self.builder = builder
        self.name_composer = name_composer
        self.value_arg = value_arg

    def default_key(self):
        return self.builder.from_tuple(self.key_template).unwrap()

    def prefix_keys(self, keys, prefix):
        new_keys = []
        for key in keys:
            new_key = key.copy()
            new_key.arg = self.name_composer(prefix, key.arg)

        return new_keys

    def singularize_list(self, statement, item_name):
        # singularize node:
        #   list => container
        if statement.keyword == 'list':
            item_node = statement.copy()
            item_node.keyword = 'container'
            item_node.raw_keyword = 'container'
            item_node.arg = item_name
            item_node = StatementWrapper(item_node, self.builder)
        else:  # leaf-list
            # singularize node:
            #   leaf-list => container with "leaf value" inside
            item_node = self.builder.container(item_name)
            value = item_node.leaf(self.value_arg)
            value.append(*statement.substmts, copy=True)

        return item_node

    def scan_list(self, statement, read_only):
        entries = []
        # should not include name of the list, use instead the name
        # of the item
        item_name = find_item_name(statement)
        accessor_path = [item_name]
        atomic_item = is_atomic_item(statement)
        include_item = is_included_item(statement)

        # a list item needs key(s) to be found. Use default if not explicit
        key_nodes = find_keys(statement)
        keys = key_nodes or [self.default_key()]

        # items should be included
        if atomic_item or include_item:
            payload = self.singularize_list(statement, item_name)
            if not key_nodes:
                # add the default key in the data structure itself
                payload.append(keys[0])

            entries.append(EntryPoint(
                accessor_path, payload=payload, own_keys=keys,
                operations=(READ_ONLY_OPS if read_only else DEFAULT_ITEM_OPS)
            ))

        # finish tree traversal for atomic items
        if atomic_item:
            return (_PRUNE, entries)

        # for children, default keys should be prefixed in order to
        # guarantee uniqueness
        keys = self.prefix_keys(keys, item_name)

        return (keys, entries)

    def scan(self, statement):
        """Find all data nodes in a tree

        .. note: experimental function: relies on ``i_children``
            undocumented feature.

        Modifiers from YANG ``accessor`` extension:
            ATOMIC, ATOMIC_ITEM, INCLUDE, INCLUDE_ITEM
        See: :module:`pyang_accessors.definitions`
        """
        # If is top-level, scan children
        if is_top_level(statement):
            ensure_validated(statement)
            children = statement.i_children
            return concat(*[self.scan(child) for child in children])

        # If not data, abort
        if not is_data(statement):
            return []

        # prepare a default entry-point
        read_only = is_read_only(statement)
        accessor_path = [statement.arg]
        entry = EntryPoint(
            accessor_path, payload=statement,
            operations=(READ_ONLY_OPS if read_only else DEFAULT_OPS),
        )

        # atomic nodes (leaf, anyxml or with `atomic` annotation)
        # should be retrieved/modified as an entire entity
        # no need to dive in tree
        if is_atomic(statement):
            return [entry]

        entries = []

        # if node has modifier `include`, add it to entry-points as
        # an entire entity
        if is_included(statement):
            entries.append(entry.copy())

        keys = None
        if is_list(statement):
            (keys, list_entries) = self.scan_list(statement, read_only)
            entries.extend(list_entries)

            if keys == _PRUNE:
                return entries

        # continue tree traversal for non-atomic
        # use `i_children`undocumented feature:
        #   - pyang resolves `uses`, `augment`, ... and store
        #     it under ``i_children``
        for child in statement.i_children:
            child_entries = self.scan(child)
            for entry in child_entries:
                if read_only:
                    entry.operations = READ_ONLY_OPS
                if keys:
                    # prepend -> according to traversal order
                    entry.parent_keys = keys + entry.parent_keys

                # prefix path with the parent path
                entry.path = accessor_path + entry.path
                entries.append(entry)

        return entries
