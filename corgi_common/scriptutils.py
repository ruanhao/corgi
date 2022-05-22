from . import run_script as _run_script, is_root, bye
from functools import partial


run_script = _run_script
run_script_live = partial(_run_script, realtime=True, opts='e')
run_script_dry = partial(_run_script, dry=True)

def run_script_as_root_live(script, dry=False):
    if dry:
        _run_script(script, realtime=True, dry=True)
        return
    if not is_root():
        bye('The script needs to be run as root.')
    _run_script(script, realtime=True)
