import inspect
import logging
from . import bye, config_logging as _config_logging


_logger = logging.getLogger(__name__)

config_logging = _config_logging

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
    if logger.isEnabledFor(logging.INFO):
        print(msg)

def debug(msg):
    frm = inspect.stack()[1]
    mod = inspect.getmodule(frm[0])
    logger = getattr(mod, 'logger', _logger)
    logger.debug(msg)
    if logger.isEnabledFor(logging.DEBUG):
        print(msg)
