# -*- coding: utf-8 -*-
"""\
Tools for generating a RPC specification from a YANG abstract syntax tree.
"""
from inflection import dasherize

from pyang.util import prefix_to_modulename_and_revision
from pyang_builder import Builder
from pyangext.definitions import HEADER_STATEMENTS, PREFIX_SEPARATOR
from pyangext.utils import create_context, qualify_str, dump

from .definitions import CHANGE_OP, ITEM_ADD_OP, ITEM_REMOVE_OP, READ_OP
from .predicates import has_prefixed_arg, is_custom_type, is_extension
from .registry import ImportRegistry
from .scan import Scanner

__author__ = "Anderson Bravalheri"
__copyright__ = "andersonbravalheri@gmail.com"
__license__ = "mozilla"


class Normalizer(object):
    """Walk the AST finding external dependencies, prefixing and importing it.
    """

    def __init__(self, ctx, registry):
        """Creates a Normalizer object

        Arguments:
            ctx (pyang.Context): Context to be used for prefix resolution.
            registry (ImportRegistry): New imports that should be used.
        """
        self.ctx = ctx
        self.registry = registry

    def namespaced_attribute(self, node, attr):
        """Re-prefix attr in node with a valid and unique prefix.

        Arguments:
            node (pyang.statements.Statement):
                Node whose attr will be re-prefixed.
            attr (str): Name of the attribute to be re-prefixed,
                e.g.: arg, keyword.

        Returns:
            tuple: (node, new_prefix, mod_name, mod_revision, attr_value)
        """
        # 1st: split attr in (current prefix, attr unprefixed name)
        (prefix, value) = qualify_str(getattr(node, attr))
        # 2nd: find module name and revision
        (name, revision) = prefix_to_modulename_and_revision(
            node.i_module, prefix, node.pos, self.ctx.errors)

        if not prefix:
            prefix = node.i_module.i_prefix

        # 3rd: add module to the import list and retrieve a new unique prefix
        prefix = self.registry.add(prefix, name, revision)

        # 4th: Change the node itself to use the new prefix!
        setattr(node, attr, PREFIX_SEPARATOR.join((prefix, value)))

        return (node, prefix, name, revision, value)

    def extension(self, node):
        """Re-prefix extension to be used in a new module."""
        node, prefix, name, _, value = self.namespaced_attribute(
            node, 'raw_keyword')

        node.keyword = (name, value)
        node.raw_keyword = (prefix, value)

        return node

    def prefixed_arg(self, node):
        """Re-prefix arg to be used in a new module."""
        node, _, _, _, _ = self.namespaced_attribute(node, 'arg')

        return node

    def external_definitions(self, parent):
        """Walk AST finding nodes that should be re-prefixed.

        This allows these nodes to be used in other modules.

        The nodes that should be re-prefixed are extensions, typedefs
        and other nodes with prefixed args (if-feature for example).

        Argument:
            parent (pyang_builder.StatementWrapper):
                Node from where the recursive search will be conducted.
        """
        # since custom type become a prefixed arg, do not run it before
        # prefixed arg hook
        parent.walk(has_prefixed_arg, self.prefixed_arg)
        parent.walk(is_custom_type, self.prefixed_arg)
        parent.walk(is_extension, self.extension)


class RPCGenerator(object):
    """Generates a YANG specification of RPC service based on an input module.

    This service provides ways of changing the deep-most
    data nodes under the original YANG module tree. Such mechanism is called
    ``accessors``.

    __Accessors__ are described as operations over the deep-most data
    data nodes under the original YANG module tree.
    Four types of ``accessors`` are provided:

    - a **READ** accessor (equivalent to a ``get`` operation),
    - a **CHANGE** accessor (equivalent to a ``set`` operation),
    - an **ITEM ADD** accessor, to add elements to a list,
    - an **ITEM_REMOVE** accessor, to remove elements from a list.

    The information transfered during RPC is listed in the table bellow,
    according to the accessor type:

    ================ =================== ==================
     accessor type        request             response
    ================ =================== ==================
     READ             parent + own keys   error || data
     CHANGE           parent keys + data  error || success
     ITEM_ADD         parent keys + data  error || own keys
     ITEM_REMOVE      keys                error || data
    ================ =================== ==================

    Here ``data`` is the value of the node itself and ``key`` is used to
    identify a node in a list.
    """
    # pylint: disable=no-member

    DEFAULT_CONFIG = {
        'key_suffix': 'id',
        'data_suffix': 'data',
        'data_and_key_suffix': 'request',
        'identification_suffix': 'identification',
        'response_suffix': 'response',
        'suffix': 'interface',
        'default_response_name': 'default-response',
        'choice_name': 'response',
        'success_name': 'success',
        'success_children_template': [
            ('leaf', 'ok', [
                ('type', 'boolean')
            ])
        ],
        'failure_name': 'failure',
        'failure_children_template': [
            ('leaf', 'error-code', [
                ('type', 'int32'),
                ('description', 'numeric code for the failure.'),
            ]),
            ('leaf', 'error-message', [
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
    """Default configuration for the generator.

    This configurations the way of how the output module is built.
    """

    def __init__(self, ctx=None, **kwargs):
        """Initialize RPC generator

        Arguments:
            ctx (pyang.Context): context to be used for module
                search/validation.
            **kwargs: configurations to override the defaults.
        """

        self.ctx = ctx or create_context()
        self.registry = None

        # set properties from kwargs or default
        for prop, default in self.DEFAULT_CONFIG.items():
            setattr(self, prop, kwargs.get(prop) or default)

    def _prefix_keys(self, keys, prefix):
        """Compose the key name with a prefix"""
        prefixed = []
        for key in keys:
            new = key.copy()
            new.arg = self.name_composer([prefix, key.arg])
            prefixed.append(key)

        return prefixed

    def _create_name(self, module, name):
        """Specify a name for the output module.

        Arguments:
            module (pyang.statements.Statement): Original module.
            name (str): None or name from the configuration options /
                command line.

        Returns:
            str: Name if specified or a suffixed version of the original
                module name.
        """
        module_name = module.arg
        joiner = '_' if '_' in module_name else '-'
        return name or joiner.join([module_name, self.suffix])

    def _create_namespace(self, module, namespace):
        """Specify a namespace for the output module.

        Arguments:
            module (pyang.statements.Statement): Original module.
            namespace (str): None or namespace from the configuration options
                / command line.

        Returns:
            str: Namespace if specified or a suffixed version of the
                original module namespace.
        """
        module_namespace = module.search_one('namespace').arg
        joiner = '/' if '://' in module_namespace else ':'
        return namespace or joiner.join([module_namespace, self.suffix])

    def _create_prefix(self, module, prefix):
        """Specify a prefix for the output module.

        Arguments:
            module (pyang.statements.Statement): Original module.
            prefix (str): None or prefix from the configuration options /
                command line.

        Returns:
            str: Prefix if specified or a suffixed version of the
                original module prefix.
        """
        module_prefix = module.search_one('prefix').arg
        joiner = '_' if '_' in module_prefix else '-'
        return prefix or joiner.join([module_prefix, self.suffix])

    def _create_module_with_header(self, module, name=None, prefix=None,
                                  namespace=None, keyword='module'):
        """Start the generation of a YANG abstract syntax tree for a module.

        Arguments:
            module (pyang.statements.Statement): Original module.
            name (str): Name for the output module.
            prefix (str): Prefix for the output module.
            namespace (str): Namespace for the output module.
            keyword (str): ``module`` or ``submodule``

        Returns:
            str: Namespace if specified or a suffixed version of the
                original module namespace.
        """
        name = self._create_name(module, name)
        prefix = self._create_prefix(module, prefix)
        namespace = self._create_namespace(module, namespace)

        # create an output module
        builder = Builder(name, keyword=keyword)
        out = builder(keyword, name)
        out_raw = out.unwrap()
        out.namespace(namespace)
        out.prefix(prefix)

        i = 2  # i is the position where the description should be placed
        # copy header statements
        for header in HEADER_STATEMENTS:
            node = module.search_one(header)
            if not node:
                continue
            if node.keyword != 'revision':
                # descriptions should be placed before revision
                i += 1
            out.append(node.copy(out_raw))

        desc = builder.description(
            self.description_template.format(module.arg), parent=out_raw)
        comment = builder.comment(self.warning_banner, parent=out_raw)

        out_raw.substmts.insert(i, comment.unwrap())
        out_raw.substmts.insert(i, desc.unwrap())

        return (out, builder)

    def _create_response_choice(self, parent, success_children=None):
        """Creates a ``choice`` node under a parent node.

        The ``choice`` node means just one child can exist at each time.
        In this case, the choice statement is used to impose the response
        status: **or there was a failure with the RPC, or it was successful**.

        Arguments:
            parent (pyang_builder.StatementWrapper):
                Node below which the ``choice`` will be placed.
            success_children (list): list of data nodes that corresponds
                to the RPC response. If no list is provided, the default
                behavior is to have an ``ok`` leaf.
        """
        choice = parent.choice(self.choice_name)

        choice.default(self.success_name)
        case = choice.case(self.success_name)
        if success_children:
            case.append(*success_children)
        else:
            case.uses(self.success_name)

        failure = choice.case(self.failure_name)
        failure.uses(self.failure_name)

        return choice

    def _define_id_grouping(self, entry):
        """Define an ID Grouping.

        The ID Grouping should be formed of all the keys necessary
        to achieve the entry-point. It should be named truncating
        the path until the last keyed item, to improve sharing.

        For exemple, consider the following YANG described strucutre::

            list user {
               list posts {
                   leaf content { type string; }
                   leaf date { type string; }
               }
            }

        Consider the entry-point "user/post/content"
        the ID Grouping should be::

            grouping user-post-identification {
               leaf user-id { type int32; }
               leaf id { type int32; }  // -> ID of post
            }

        The same ID Grouping shoud shared with entry-point "user/post/date".

        The last key should not be prefixed, but the predecessors should,
        in order to guarantee uniqueness.

        .. note:: This method do not actually create the complete ``grouping``
            just returns its name and content

        Arguments:
            entry: entry-point generated by scanner.

        Returns:
            group_name (str): the name of the grouping created.
            content (list): key nodes that uniquelly references the entry-point.
        """
        group_name = None
        path = entry.path
        parent_keys = entry.parent_keys

        # get the name of the nodes who have keys in the order they appear
        keyed_items = [name for name in path if name in parent_keys]
        if entry.own_keys:
            keyed_items.append(entry.path[-1])  # add the item name itself

        if not keyed_items:
            return (None, [])

        target = keyed_items[-1]  # <= last keyed item
        target_keys = parent_keys.get(target) or entry.own_keys

        # truncate the path before the last keyed item
        predecessor_names = []
        for name in path:
            if name == target:
                break
            predecessor_names.append(name)

        # predecessor keys should be prefixed in order to
        # guarantee uniqueness
        predecessor_keys = []
        for (name, keys) in parent_keys.items():
            if name in predecessor_names:
                keys = self._prefix_keys(keys, name)
            predecessor_keys.extend(keys)

        group_name = self.name_composer(
            predecessor_names + [target, self.identification_suffix])

        return (group_name, predecessor_keys + target_keys)

    @staticmethod
    def _create_and_append_grouping(parent, name, content, registry):
        """Create a new grouping and appends to the output if not present.

        Arguments:
            out: the parent node
            name: argument for the grouping
            content (list): children to be appended
        """
        if name and name not in registry:
            parent.grouping(name, content)
            registry.append(name)

    @staticmethod
    def _create_imports(module, builder, registry):
        """Add imports from a registry to a module"""
        raw_node = module.unwrap()
        substmts = raw_node.substmts

        # iterate in the reverse order, so each new import can be placed
        # at the top of the previous, and in the end the order will
        # be corrected
        registry_data = registry.by_prefix.items()
        for (prefix, (module_name, revision)) in reversed(registry_data):
            # creates a new import
            import_node = builder(
                'import', module_name, ('prefix', prefix), parent=raw_node)

            if revision and revision != 'unknown':
                import_node.revision(revision, parent=raw_node)

            # the 1st node is the namespace
            # the 2st node is the prefix
            # all the import nodes should be after it
            substmts.insert(2, import_node.unwrap())

    def transform(self, module,
                  name=None, prefix=None, namespace=None,
                  keyword='module'):
        """Creates a RPC service definition from a YANG module.

        Given a input YANG module, this method generates an associated
        service specification for accessing its data nodes, as another
        related YANG module.

        For example, if the original module has an leaf named ``username``,
        the generated module will have two RPC nodes: ``set-username`` and
        ``get-username``.

        Arguments:
            module (pyang.statements.Statement):
                Original module that describes the data structure.
            name (str): Name for the output module **(optional)**.
            prefix (str): Prefix for the output module **(optional)**.
            namespace (str): Namespace for the output module **(optional)**.
            keyword (str): ``module`` or ``submodule`` (see YANG RFC).
                The default value is ``module``.

        If no ``name``, ``prefix`` or ``namespace`` is passed, the default
        behavior is composing it from the original module attributes.
        In order to perform this composition, a suffix is added to the
        retrieved attributes. This suffix can be changed by changing the
        object attribute ``suffix`` and the default value is __interface__.
        The way this combination is performed depends on other attribute, the
        ``name_composer``, a function which receives an array and should
        return a string (the default function dasherizes the result). Both
        attributes can be changed directly in the instance object, or by
        passing named parameters to the object constructor.

        Returns:
            pyang_builder.StatementWrapper: Abstract Syntax Tree for the
                output module. This AST can be turned into a string by
                calling the
                :meth:`.dump() <pyang_builder.builder.Builder.dump>` method.
        """

        (out, builder) = self._create_module_with_header(module, name, prefix,
                                                         namespace, keyword)

        scanner = Scanner(
            builder, self.key_template,
            self.name_composer, self.key_suffix, self.value_arg)

        entries = scanner.scan(module)
        if not entries:
            return out

        compose = self.name_composer

        # registry of groupings already created
        already_created = []

        # all response messages should have optional failure nodes
        # these nodes is determined by `failure_children_template` option
        failure_name = self.failure_name
        failure_content = self.failure_children_template

        # Default dumb success nodes are also required, because CHANGE
        # operations return it
        success_name = self.default_response_name
        success_content = self.success_children_template


        for entry in scanner.scan(module):
            # The ID Grouping is used by READ and ITEM_REMOVE operations
            # since it is necessary to specify which node is the target
            (id_group, keys) = self._define_id_grouping(entry)

            # Data Grouping is always present because READ is always present
            # and it is the response
            data_group = compose(entry.path + [self.data_suffix])

            # For CHANGE + ITEM_ADD operations it is necessary to specify
            # both the the keys to achieve the node and
            # the data inserted/changed
            # It is important to note that own keys are already present
            # inside data. So if there is no parent keys, this group is
            # unecessary
            parent_id_group = None
            parent_id_content = None
            if entry.parent_keys:
                fake_entry = entry.copy()
                fake_entry.own_keys = None

                parent_id_group, parent_id_content = (
                    self._define_id_grouping(fake_entry)
                )

                # data_and_id_group = compose(
                #     entry.path + [self.data_and_key_suffix])

                # data_and_id = parent_keys + [builder.uses(data_group)]

            for operation in entry.operations:
                # ================ =================== ==================
                # accessor type         request             response
                # ================ =================== ==================
                # READ             parent + own keys   error || data
                # CHANGE           parent keys + data  error || success
                # ITEM_ADD         parent keys + data  error || own keys
                # ITEM_REMOVE      keys                error || data
                # ================ =================== ==================

                rpc_name = compose([operation] + entry.path)
                request_name = None
                request_content = None
                response_name = None
                response_content = None

                if any(op == operation for op in (READ_OP, ITEM_REMOVE_OP)):
                    # READ/REMOVE request may specify parent + own keys
                    # (id_group).
                    request_name = id_group
                    request_content = keys
                    # Responds with data
                    response_name = (
                        compose(entry.path + [self.response_suffix]))
                    self._create_and_append_grouping(
                        out, data_group, entry.payload, already_created)
                    response_content = [builder.uses(data_group)]
                else:  # CHANGE_OP, ITEM_ADD_OP
                    # CHANGE/ADD request may specify parent + own keys and
                    # must specify data.
                    # own keys are already present in the payload (data_group)
                    request_name = parent_id_group or data_group
                    request_content = parent_id_content or entry.payload

                if operation == CHANGE_OP:
                    # CHANGE request does not respond anything
                    # (except occasional error)
                    response_name = success_name
                    response_content = success_content
                elif operation == ITEM_ADD_OP:
                    # ADD request responds with own keys
                    response_name = compose([rpc_name, self.response_suffix])
                    response_content = (
                        [builder.uses(id_group)] if not parent_id_content
                        else entry.own_keys
                    )

                # self._create_response_choice()

                self._create_and_append_grouping(
                        out, request_name, request_content, already_created)
                self._create_and_append_grouping(
                        out, response_name, response_content, already_created)
                rpc = out.rpc(rpc_name)
                if request_name:
                    rpc.input().uses(request_name)
                if response_name:
                    rpc.output().uses(response_name)

        registry = ImportRegistry()
        normalize = Normalizer(self.ctx, registry)
        normalize.external_definitions(out)
        self._create_imports(out, builder, registry)

        out.validate(self.ctx, rescue=True)

        return out
