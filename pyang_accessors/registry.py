# -*- coding: utf-8 -*-
"""
"""
from __future__ import unicode_literals

import inflection

from pyangext.definitions import URL_SEPARATOR

from .exceptions import YangImportError

__author__ = "Anderson Bravalheri"
__copyright__ = "Copyright (C) 2016 Anderson Bravalheri"
__license__ = "mozilla"


def prefixify(name, separator='-'):
    """Creates a valid prefix from module name or namespace"""
    # remove urn
    name = name.replace('http://', '').replace('urn:', '')

    # remove base URL if it exists
    if URL_SEPARATOR in name:
        name = name.split(URL_SEPARATOR)[1:]

    # remove strange characters
    return inflection.parameterize(
        ''+name, separator  # ensure unicode for both py2, py3
                            # thanks to __futue__ literals are unicode,
                            # and unicode + str => unicode
    )


class ImportRegistry(object):
    """Store information about the import statements in a YANG module.

    This class can be used to manage prefixes and revisions of the
    imported module.

    Attributes:
        by_prefix (dict): ``prefix -> (module_name, revision)``
        by_name (dict): ``module_name -> (prefix, revision)``
        prefixes_reserved (list): list of prefixes disallowed.
    """

    def __init__(self):
        """Initialize the registry"""
        # Indexes
        self.by_prefix = {}
        self.by_name = {}
        # Collisions counters
        self.prefix_request = {}
        self.prefixes_reserved = []

    def add(self, prefix, name, revision):
        """Add a module in the prefix registry.

        Arguments:
            prefix (str): A suggestion about what prefix to use.
                Not necessarly it will be used...
            name (str): module name
            revision (str): identification of the module revision.

        Raises:
            YangImportError: If the module cannot be imported.

        Returns:
            str: The prefix that should be used for the module.
        """
        # See if module was already registed
        some_prefix, some_revision = self.by_name.get(name, (None, None))

        if some_revision and some_revision != revision:
            raise YangImportError(
                'Cannot import the same module with two different revisions.'
                ' %s requested, but %s already imported!',
                some_revision, revision)

        if some_prefix:
            return some_prefix

        if not prefix:
            prefix = prefixify(name)

        occurencies = self.prefix_request.get(prefix, 0) + 1

        if occurencies > 1:
            # Increment the number of colisions because 2 different modules
            # are trying to use the same prefix.
            self.prefix_request[prefix] = occurencies
            # Generate a brand new prefix, by adding the counter
            prefix += str(occurencies)

        # In this point of method, the prefix is guaranteed to be fresh
        self.prefix_request[prefix] = 1
        self.by_prefix[prefix] = (name, revision)
        self.by_name[name] = (prefix, revision)

        return prefix

    def reserve_prefix(self, *prefixes):
        """After reserved prefix, cannot be taken"""

        for prefix in prefixes:
            self.prefixes_reserved.append(prefix)
            self.prefix_request[prefix] = 1
