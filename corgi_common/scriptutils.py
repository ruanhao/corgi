from . import run_script as _run_script
from functools import partial


run_script = _run_script
run_script_live = partial(_run_script, realtime=True, opts='e')
run_script_dry = partial(_run_script, dry=True)
