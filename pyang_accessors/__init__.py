# -*- coding: utf-8 -*-
"""PYANG extension for generating derived modules.

The derived modules define RPCs for each leaf of the original module.
"""
import pkg_resources

from .exceptions import YangImportError
from .generators import RPCGenerator
from .registry import ImportRegistry
from .scan import Scanner

try:
    __version__ = pkg_resources.get_distribution(__name__).version
except:  # pylint: disable=bare-except
    __version__ = 'unknown'

__all__ = ['RPCGenerator', 'ImportRegistry', 'Scanner', 'YangImportError']
