import pkg_resources

try:
    __version__ = pkg_resources.get_distribution(__name__).version
except:
    __version__ = 'unknown'

from .exceptions import YangImportError
from .generators import RPCGenerator
from .registry import ImportRegistry
from .scan import Scanner

__all__ = ['RPCGenerator', 'ImportRegistry', 'Scanner', 'YangImportError']
