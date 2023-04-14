from . import run_script as _run_script, is_root, bye
from functools import partial
import subprocess
import click


run_script = _run_script
run_script_live = partial(_run_script, realtime=True, opts='e')
run_script_dry = partial(_run_script, dry=True)

def try_run_script_as_root(script, dry=False, **kwargs):
    if dry:
        _run_script(script, dry=True)
        return
    if not is_root():
        raise Exception("Not root.")
    return _run_script(script, **kwargs)

def run_script_as_root_live(script, dry=False):
    if dry:
        _run_script(script, realtime=True, dry=True)
        return
    if not is_root():
        bye('The script needs to be run as root.')
    _run_script(script, realtime=True)

def write_to_clipboard(output):
    process = subprocess.Popen('pbcopy', env={'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE)
    process.communicate(output.encode())

def pause(msg='Press Enter to continue...'):
    input(msg)

def confirm(abort=False):
    return click.confirm('Do you want to continue?', abort=abort)

def prompt(msg='Please enter:', type=str, default=None):
    value = click.prompt(msg, type=type, default=default)
    return value
