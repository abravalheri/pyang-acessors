# -*- coding: utf-8 -*-
"""\
Tools for searching a YANG module looking for nodes that can be accessed.
"""
from itertools import chain as concat

from inflection import singularize

from pyang_builder import ListWrapper
from pyangext.utils import find, select

from .definitions import (  # constants and identifiers
    CHANGE_OP,
    ITEM_ADD_OP,
    ITEM_NAME,
    ITEM_REMOVE_OP,
    READ_OP
)
from .predicates import (
    is_atomic,
    is_atomic_item,
    is_data,
    is_included,
    is_included_item,
    is_leaf_list,
    is_list,
    is_read_only,
    is_top_level
)

# create a unique object for comparison
_PRUNE = GeneratorExit()

READ_ONLY_OPS = [READ_OP]
DEFAULT_OPS = READ_ONLY_OPS + [CHANGE_OP]
DEFAULT_ITEM_OPS = DEFAULT_OPS + [ITEM_ADD_OP, ITEM_REMOVE_OP]


def ensure_validated(statement):
    """Make sure the statement was validated.

    ... and has the required undocumented magical lovely
    ``i_..`` strange attributes.
    """
    if not (hasattr(statement, 'i_is_validated') and
            statement.i_is_validated):
        raise AttributeError(
            'Invalid module %s. Was the module validated?', statement.arg)


def find_keys(statement):
    """Find the key nodes for a list, specified in the ``key`` statement."""
    key = statement.search_one('key')

    return key and [
        select(statement.i_children, arg=name)[0]
        for name in key.arg.split(' ')
    ]


def find_item_name(statement):
    """Discover the singular name of the item in list."""
    # should not include name of the list, use instead the name
    # of the item
    item_name = find(statement, ITEM_NAME, ignore_prefix=True)
    if item_name:
        print item_name[0].arg
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
        payload (pyang.statements.Statement or list):
            statements that define the data under the node
        parent_keys (dict): If any parent of the target link is an element
            of a list, its key is added to this dict by item name
        own_keys: list of keys for the target node
    """

    def __init__(self, path,
                 payload=None, operations=None,
                 parent_keys=None, own_keys=None):
        """Normalize input data (add defaults)"""
        if operations is None:
            operations = [READ_OP]
        if parent_keys is None:
            parent_keys = {}
        if own_keys is None:
            own_keys = []

        self.path = path
        self.payload = payload
        self.operations = operations
        self.parent_keys = parent_keys
        self.own_keys = own_keys

    def __repr__(self):
        """String representation for debugging support"""
        return '\n'.join([
            '<{}.{} at {} ('.format(
                self.__module__, self.__class__.__name__, hex(id(self))),
            '\tpath: ' + repr(self.path),
            '\tpayload: ' + repr((self.payload.keyword, self.payload.arg)),
            '\toperations: ' + repr(self.operations),
            '\tparent_keys: ' + repr(self.parent_keys),
            '\town_keys: ' + repr(self.own_keys),
            ')>',
        ])

    def copy(self):
        """Copy the entry-point avoiding overriding it."""

        payload = self.payload and (
            self.payload.invoke('copy')
            if isinstance(self.payload, ListWrapper)
            else self.payload.copy()
        )

        return type(self)(
            self.path,
            payload,
            self.operations[:],
            self.parent_keys.copy(),
            self.own_keys[:])


class Scanner(object):
    """Scan a YANG module looking for the deep-most data nodes.

    After finding eligible node, its path is recorded, as well as each
    key (including parents') needed to achieve it again.
    From this information a list of entry-points is generated.

    Each entry-point corresponds to a target for one or more ``accessors``
    that will be generated.

    The main method of this class is the :meth:`~Scanner.scan`
    and the other methods, classes or functions of the module are designed
    to support it.
    """

    def __init__(self, builder, key_template,
                 name_composer, key_name=None, value_arg='value'):
        """Initialize the scanner object.

        Arguments:
            builder (pyang_builder.Builder): Object used to generate nodes.
            key_template (tuple): Template of the default ``key`` node.
                When a list do not specify its key, an implicit node is
                generated. The default value is
                ``('leaf', 'id', [('type', 'int32')])`` which is equivalent
                to the yang statement ``leaf id { type int32; }``.
                See :meth:`pyang_builder.Builder.from_tuple`.
            key_name (str): Name of the default key. If it is passed the
                argument of the node generated with ``key_template``
                will be changed to it.
            name_composer (function): Callable object used to compose a new
                name from a list of other names. It is mainly used to compose
                the default key name for the parent nodes,
                e.g. ``['user', 'id'] -> 'user-id'``.
            value_arg (str): When a entry is produced for a value in a
                leaf-list, it is necessary to transform the plain data node
                in a complex container, in order to introduce the implicit key.
                This argument is used to create a new leaf that will store the
                data value. For example, consider the data node
                ``leaf-list usernames { type string; }``, the produced entry
                for an ``value_arg = 'value'`` and the default ``key_template``
                is::

                    container username {
                        leaf id { type int32; }
                        leaf value { type string; }
                    }

        Returns:
            list: :class:`EntryPoint` elements.
        """
        self.key_template = key_template
        self.builder = builder
        self.key_name = key_name
        self.name_composer = name_composer
        self.value_arg = value_arg

    def default_key(self):
        """Render the default key template into a Statement"""
        key = self.builder.from_tuple(self.key_template).unwrap()
        if self.key_name:
            key.arg = self.key_name
        return key

    def singularize_list(self, statement, item_name):
        """Generates a data description for one element of the list."""
        if is_leaf_list(statement):
            # singularize node:
            #   leaf-list => container with "leaf value" inside
            item_node = self.builder.container(item_name)
            value = item_node.leaf(self.value_arg)
            value.append(*statement.substmts, copy=True)
        else:
            # singularize node:
            #   list => container
            item_node = statement.copy()
            item_node.keyword = 'container'
            item_node.raw_keyword = 'container'
            item_node.arg = item_name
            item_node = self.builder(item_node)

        return item_node

    def scan_list(self, statement, read_only):
        """Scans a list looking for entry-points"""
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
            return (_PRUNE, entries, accessor_path)

        return (keys, entries, accessor_path)

    def scan(self, statement):
        """Generates a list of entry-points for the deep-most data nodes.

        .. note: experimental function: relies on ``i_children``
            undocumented feature.

        The default behavior is just include entry-points for the ``leaf``
        and ``leaf-list`` nodes. ``READ`` and ``CHANGE``
        (unless ``config false;``) operations are defined by default.
        ``ITEM_ADD`` and ``ITEM_REMOVE`` are additionally
        defined for ``leaf-list`` nodes.

        The extensions defined in the ``pyang-accessors.yang`` can be used
        to control the scanner behavior.
        This extensions define the following modifiers::

            ATOMIC, ATOMIC_ITEM, INCLUDE, INCLUDE_ITEM

        .. seealso: extensions :module:`pyang_accessors.definitions`
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
            (keys, list_entries, accessor_path) = self.scan_list(
                statement, read_only)
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
                    parent_name = accessor_path[-1]
                    node_name = entry.path[-1]
                    key_names = [key.arg for key in keys]
                    # keys cannot be changed
                    # and there is no sense in reading it, because they are
                    # necessary to do this operation
                    # therefore, skip keys
                    if node_name in key_names:
                        continue

                    # relate keys with the last node name
                    entry.parent_keys[parent_name] = keys

                # prefix path with the parent path
                entry.path = accessor_path + entry.path
                entries.append(entry)

        return entries
