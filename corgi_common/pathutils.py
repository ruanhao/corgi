import os
import inspect

def get_local_file_path(filename):
    frm = inspect.stack()[1]
    mod = inspect.getmodule(frm[0])
    return os.path.join(get_module_path(mod), filename)

def get_module_path(mod=None):
    if not mod:
        frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])
    return os.path.dirname(mod.__file__)
