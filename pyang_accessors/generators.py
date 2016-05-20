# -*- coding: utf-8 -*-
"""
"""
import sys
import logging
from itertools import chain as concat

from inflection import singularize, dasherize

from pyangext.syntax_tree import YangBuilder, find, select
from pyangext.utils import create_context
from pyangext.definitions import HEADER_STATEMENTS, DATA_STATEMENTS

from pyang_accessors import __version__

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"

READ_ONLY_OPERATIONS = ['get']
DEFAULT_OPERATIONS = ['get', 'set']
LIST_OPERATIONS = ['add', 'remove']


def merge(*args, **kwargs):
    """Merge 2 or more dicts.

    Arguments:
        *args: dicts to be merged
        **kwargs: will be transformed in a dict and merged
            with higher precedence.

    Returns:
        dict
    """
    return reduce(
        lambda acc, x: acc.update(x) or acc,
        args + [kwargs], {})

# Modifiers:
# include, atomic, atomic-item
# atomic-item => item-name


def scan(statement, default_key='id'):
    """Find all data nodes in a tree

    Modifiers:
        'atomic'
        'atomic-item'
        'include'
        'include-item'
        'manage-items'

    ``descriptor`` is a dict with keys: ``path``, ``payload``, ``operations``.
    Path is a list with names of nodes and tuples of keys, required to
    access the node. Payload describes the data within the node. Operations is
    a list of allowed access types on node.
    """
    # NOTE: experimental function: relies on ``i_children``
    # undocumented feature.

    # If is top-level, scan children
    keyword = statement.keyword

    if keyword in ('module', 'submodule'):
        return concat(
            *(scan(child, default_key) for child in statement.i_children)
        )

    # If not data, abort
    if keyword not in DATA_STATEMENTS:
        return []

    config = statement.search_one('config')
    read_only = config and ('false' in config.arg)

    # default entry-point description
    accessor_path = [statement.arg]
    entry_point = {
        'path': accessor_path,
        'payload': statement,
        'operations':
            READ_ONLY_OPERATIONS if read_only else DEFAULT_OPERATIONS[:],
    }

    # atomic nodes (leaf, anyxml or with `atomic` annotation)
    # should be retrieved/modified as an entire entity
    # no need to process anything
    if (keyword in ('leaf', 'anyxml') or
            find(statement, 'modifier', 'atomic', ignore_prefix=True)):
         return [entry_point]

    entries = []

    # if node has modifier `include`, add it to entry-points as
    # an entire entity
    if find(statement, 'modifier', 'include', ignore_prefix=True):
        entries.append(entry_point.copy())

    if keyword in ('list', 'leaf-list'):
        # should not include name of the list, use instead the name
        # of the item
        item_name = find(statement, 'item-name')
        if item_name:
            item_name = item_name[0].arg
        else:
            item_name = singularize(statement.arg)
        accessor_path = [item_name]
        key = statement.search_one('key')
        # append key as a tuple in the path, so it is easily recognized
        if key:
            accessor_path.append(tuple(
                select(statement.i_children, arg=name)[0]
                for name in key.arg.split(' ')
            ))
        else:
            accessor_path.append(tuple(default_key))

        atomic_item = find(
            statement, 'modifier', 'atomic-item', ignore_prefix=True)
        include_item = find(
            statement, 'modifier', 'include-item', ignore_prefix=True)

        # items should be included
        if atomic_item or include_item:
            # singularize node:
            #   list => container
            #   leaf-list => leaf
            payload = statement.copy()
            payload.keyword = 'container' if keyword == 'list' else 'leaf'
            payload.raw_keyword = new.keyword
            payload.arg = item_name

            entries.append({
                'path': accessor_path,
                'payload': payload,
                # read-only items cannot be added or removed
                'operations': (
                    READ_ONLY_OPERATIONS if read_only
                    else concat(entry_point['operations'], LIST_OPERATIONS)
                ),
            })

        # finish tree traversal for atomic items
        if atomic_item:
            return entries

    # continue tree traversal
    # use i_children because it is already resolved
    if not hasattr(statement, 'i_children'):
        raise AttributeError(
            'statement has no attribute `i_children`. '
            'Was the module validated?')

    for child in statement.i_children:
        items = scan(child, default_key)
        entries.extend(items)
        for item in items:
            item['path'] = accessor_path + item['path']
            if read_only:
                item['operations'] = READ_ONLY_OPERATIONS

    return entries


class RPCGenerator(object):
    """Generates a new YANG module with accessors for the input module.

    RPC getter/setter each leaf of the input module

    Attributes:
        input_grouping_suffix (str):
        output_grouping_suffix (str):
        error_container_name (str):
    """

    DEFAULT_CONFIG = {
        'input_grouping_suffix': 'request',
        'output_grouping_suffix': 'response',
        'suffix': 'interface',
        'default_key': 'id',
        'key_mixin_template': (
            ('leaf', '{}', [
                ('type', 'int32'),
            ])
        ),
        'error_mixin': (
            ('container', 'error', [
                ('leaf', 'code', [('type', 'int32')]),
                ('leaf', 'message', [('type', 'string')]),
            ])
        ),
        'name_composer': lambda names: dasherize('_'.join(names)),
        'warning_banner': (
            '--------------------- DO NOT MODIFY! ---------------------\n'
            '|                                                        |\n'
            '|  File automatically generated using `pyang-accessors`. |\n'
            '|                                                        |\n'
            '----------------------------------------------------------'
        ),
        'description_template': 'Accessors interface for module: `{}`.',
    }

    def __init__(self, ctx=None, **kwargs):
        """

        Keyword Arguments:
            input_grouping_suffix
            output_grouping_suffix
            error_mixin
            default_key
            name_composer func(array) -> string, default is dasherize
        """

        self.ctx = ctx or create_context()

        # set properties from kwargs or default
        for prop, default in self.DEFAULT_CONFIG.items():
            setattr(self, prop, kwargs.get(prop) or default)

    def create_name(self, module, name):
        module_name = module.arg
        joiner = '_' if '_' in module_name else '-'
        return name or joiner.join([module_name, self.suffix])

    def create_namespace(self, module, namespace):
        module_namespace = module.search_one('namespace').arg
        joiner = '/' if '://' in module_namespace else ':'
        return namespace or joiner.join([module_namespace, self.suffix])

    def create_prefix(self, module, prefix):
        module_prefix = module.search_one('prefix').arg
        joiner = '_' if '_' in module_prefix else '-'
        return prefix or joiner.join([module_prefix, self.suffix])

    def transform(self, module,
                  name=None, prefix=None, namespace=None,
                  keyword='module'):
        name = self.create_name(module, name)
        prefix = self.create_prefix(module, prefix)
        namespace = self.create_namespace(module, namespace)

        # create an output module
        builder = YangBuilder(name, keyword=keyword)
        out = builder(keyword, name)
        out_raw = out.unwrap()
        out.namespace(namespace)
        out.prefix(prefix)

        out.comment(self.warning_banner)

        # copy header statements
        for header in HEADER_STATEMENTS:
            node = module.search_one(header)
            if not node:
                continue
            out.append(node.copy(out_raw))

        out.description(self.description_template.format(module.arg))

        # all response messages should have and optional error node
        # this error node is determined by `error_mixin` option
        error = builder.from_tuple(self.error_mixin).unwrap()

        for entry_point in scan(module, self.default_key):
            path = entry_point['path']
            payload = entry_point['payload']
            operations = entry_point['operations']

            # First it is necessary to extract the extra input
            # parameters for path, since the keys necessary to choose
            # the correct items in lists.
            #
            # Keys are added to path as tuples in order to be recognized

            default_key_indicative = tuple(self.default_key)
            default_key_counter = path.count(default_key_indicative)
            previous = ''
            name = []
            input_param = []
            for part in path:
                if part == default_key_indicative:
                    # Nodes in the same hierarchy level should not have
                    # the same name. If there is more than one default-key
                    # it is necessary to prepend it with the name
                    # of the list item.
                    # The last default-key can be left as it is.
                    default_key_counter -= 1
                    if default_key_counter == 0:
                        key = self.default_key
                    else:
                        key = self.name_composer([previous, self.default_key])

                    # when a default-key is used, it is necessary to
                    # generate a node for it, using template
                    input_param.append(builder.from_tuple((
                        self.key_mixin_template[0],
                        key,
                        self.key_mixin_template[1],
                    ).unwrap()))
                elif isinstance(part, tuple):
                    # Scanner already add the nodes for keys specified in YANG
                    for key_node in part:
                        input_param.append(key_node)
                else:
                    # If it is not a tuple, its just a node name and no
                    # input parameter is necessary
                    name.append(part)

                previous = part

            # for each operation generate an grouping for input,
            # an grouping for output and an rpc node
            for operation in operations:
                operation_path = [operation] + path
                input_grouping_name = self.name_composer(
                    operation_path + [self.input_grouping_suffix])
                output_grouping_name = self.name_composer(
                    operation_path + [self.output_grouping_suffix])

                input_grouping_contents = []
                if input_param or operation:
                    input_grouping_contents = list(concat(
                        input_grouping_contents, *input_param))

                if operation in ('set', 'add'):
                    input_grouping_contents.append(payload)

                if input_grouping_contents:
                    input_grouping = out.grouping(input_grouping_name)
                    input_grouping.append(*input_grouping_contents, copy=True)

                output_grouping = out.grouping(output_grouping_name)
                output_grouping.append(error, copy=True)

                if operation in ('get', 'remove'):
                    output_grouping.append(payload, copy=True)

                rpc = out.rpc(self.name_composer(operation_path))
                if input_grouping_contents:
                    rpc.input().uses(input_grouping_name)
                rpc.output().uses(output_grouping_name)

        return out
