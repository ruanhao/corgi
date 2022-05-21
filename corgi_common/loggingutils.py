import inspect
import logging
from . import bye, goodbye

_logger = logging.getLogger(__name__)


def fatal(msg):
    frm = inspect.stack()[1]
    mod = inspect.getmodule(frm[0])
    logger = getattr(mod, 'logger', _logger)
    logger.critical(msg)
    bye(msg)


def info(msg):
    frm = inspect.stack()[1]
    mod = inspect.getmodule(frm[0])
    logger = getattr(mod, 'logger', _logger)
    logger.info(msg)
    print(msg)
