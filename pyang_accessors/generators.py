# -*- coding: utf-8 -*-
"""
"""
from inflection import dasherize

from pyangext.definitions import HEADER_STATEMENTS
from pyangext.utils import create_context
from pyang_builder import Builder

from .definitions import (
    CHANGE_OP,
    ITEM_ADD_OP,
    ITEM_REMOVE_OP,
    READ_OP,
)
from .scan import Scanner

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"


class RPCGenerator(object):
    """Generates a new YANG module with accessors for the input module.

    RPC getter/setter each leaf of the input module

    Attributes:
        input_grouping_suffix (str):
        output_grouping_suffix (str):
        error_container_name (str):
    """

    DEFAULT_CONFIG = {
        'id_suffix': 'id',
        'data_suffix': 'data',
        'data_and_id_suffix': 'full-data',
        'suffix': 'interface',
        'choice_name': 'response',
        'success_name': 'success',
        'failure_name': 'failure',
        'failure_children_template': [
            ('leaf', 'error-code', [
                ('type', 'int32'),
                ('description', 'numeric code for the failure.'),
            ]),
            ('leaf', 'message', [
                ('type', 'string'),
                ('description', 'textual description of failure.')
            ]),
        ],
        'key_template':
            ('leaf', 'id', [
                ('type', 'int32'),
            ]),
        'name_composer':
            lambda names: dasherize('_'.join(x for x in names if x)),
        'warning_banner': (
            '--------------------- DO NOT MODIFY! ---------------------\n'
            '|                                                        |\n'
            '|  File automatically generated using `pyang-accessors`. |\n'
            '|                                                        |\n'
            '----------------------------------------------------------'
        ),
        'description_template': 'Accessors interface for module: `{}`.',
        'value_arg': 'value',
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


    def create_module_with_header(self, module, name=None, prefix=None,
                                  namespace=None, keyword='module'):
        name = self.create_name(module, name)
        prefix = self.create_prefix(module, prefix)
        namespace = self.create_namespace(module, namespace)

        # create an output module
        builder = Builder(name, keyword=keyword)
        out = builder(keyword, name)
        out_raw = out.unwrap()
        out.namespace(namespace)
        out.prefix(prefix)

        # copy header statements
        for header in HEADER_STATEMENTS:
            node = module.search_one(header)
            if not node:
                continue
            out.append(node.copy(out_raw))

        # desc = out.description(self.description_template.format(module.arg))
        # desc.comment(self.warning_banner)

        return (out, builder)

    def create_response_choice(self, parent, success_children=None):
        choice = parent.choice(self.choice_name)

        if success_children:
            choice.default(self.success_name)
            case = choice.case(self.success_name)
            case.append(*success_children)

        failure = choice.case(self.failure_name)
        failure.uses(self.failure_name)

        return choice

    def transform(self, module,
                  name=None, prefix=None, namespace=None,
                  keyword='module'):

        (out, builder) = self.create_module_with_header(module, name, prefix,
                                                        namespace, keyword)

        scanner = Scanner(
            builder, self.key_template, self.name_composer, self.value_arg)

        entries = scanner.scan(module)
        if not entries:
            return out

        # all response messages should have optional failure nodes
        # these nodes is determined by `failure_children_template` option
        failure = builder.grouping(
            self.failure_name, self.failure_children_template, parent=out
        )
        out.append(failure)
        print list(scanner.scan(module))

        for entry in scanner.scan(module):
            # id group is just present if keys are not empty
            id_group = None
            keys = entry.parent_keys + entry.own_keys
            if keys:
                id_group = self.name_composer(
                    entry.path + [self.id_suffix])
                print '# - keys', keys
                out.grouping(id_group).append(*keys)

            # data grouping is always present because READ is always present
            data_group = self.name_composer(entry.path + [self.data_suffix])
            out.grouping(data_group, entry.payload)

            data_and_id_group = None
            if entry.parent_keys:
                data_and_id_group = self.name_composer(
                    entry.path + [self.data_and_id_suffix])
                group = out.grouping(
                    data_and_id_group, entry.parent_keys)
                group.uses(data_group)

            for operation in entry.operations:
                # --- OPERATIONS ---
                rpc = out.rpc(self.name_composer([operation] + entry.path))
                if any(op == operation for op in (READ_OP, ITEM_REMOVE_OP)):
                    # READ/REMOVE request may specify parent + own keys
                    # (id_group).
                    if id_group:
                        rpc.input().uses(id_group)
                    # Responds with data
                    self.create_response_choice(
                        rpc.output(), [builder.uses(data_group)])
                else:  # CHANGE_OP, ITEM_ADD_OP
                    # CHANGE/ADD request may specify parent + own keys and
                    # must specify data.
                    # own keys are already present in the payload (data_group)
                    rpc.input().uses(
                        (data_and_id_group if data_and_id_group else data_group)
                    )

                if operation == CHANGE_OP:
                    # CHANGE request does not respond anything
                    # (except occasional error)
                    self.create_response_choice(rpc.output())
                elif operation == ITEM_ADD_OP:
                    # ADD request responds with own keys
                    id_group_is_own_key = (
                        len(keys) == 1 and keys[0] == entry.own_keys[0])
                    self.create_response_choice(
                        rpc.output(),
                        [builder.uses(id_group)] if id_group_is_own_key
                        else entry.own_keys
                    )

        return out
