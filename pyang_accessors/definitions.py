# -*- coding: utf-8 -*-
"""Meta information about accessors."""

__author__ = "Anderson Bravalheri"
__copyright__ = "Copyright (C) 2016 Anderson Bravalheri"
__license__ = "mozilla"

# -- Operations

READ_OP = 'get'
"""``get`` operation - reads a node value"""

CHANGE_OP = 'set'
"""``set`` operation -  changes a node value"""

ITEM_ADD_OP = 'add'
"""``add`` operation - add a child in a node"""

ITEM_REMOVE_OP = 'remove'
"""``remove`` operation -  removes a child from a node"""

# -- Extension

MODIFIER_EXT = 'modifier'
"""``pyang-accessor`` YANG extension keyword.

The default behavior of ``pyang-accessor`` is
just produce accessors for leafs and leaf-lists elements.

This extension change this behavior, permitting accessors
for nested complex nodes.
"""

ATOMIC = 'atomic'
"""Value for ``pyang-accessor`` YANG modifier keyword.

With this annotation, a list or container will be considered
an indivisible entity.

``set``/``get`` operations will replace/retrieve the entire
entity at once.
"""

ATOMIC_ITEM = 'atomic-item'
"""Value for ``pyang-accessor`` YANG modifier keyword.

Similar to `atomic`, but consider each item of a list
an indivisible entity instead of the entire list.

Two extra operations are added for non-read-only
items: ``add`` and ``remove``.

The ``add`` operation should receive a single entity
(list item), while the ``remove`` operation will return one.

This is the default behavior for leaf-lists.
"""

INCLUDE = 'include'
"""Value for ``pyang-accessor`` YANG modifier keyword.

Add accessors to retrieve(``get``) or replace(``set``)
the entire leaf-list, list or container node.

With this annotation, sub-nodes can still be accessed individually.
"""

INCLUDE_ITEM = 'include-item'
"""Value for ``pyang-accessor`` YANG modifier keyword.

Similar to ``include``, but consider each item of a list
an entity instead of the entire list. Like :data:`ATOMIC`,
adds ``add`` and ``remove`` operations.

See :data:`INCLUDE`.
"""

ITEM_NAME = 'item-name'
"""Name for an item of a list.
The default behavior is assume the singularized list name.
"""