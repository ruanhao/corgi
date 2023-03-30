import logging
from functools import wraps
import click
from stopwatch import Stopwatch

logger = logging.getLogger(__name__)

def simple_timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        stopwatch = Stopwatch(2)
        result = f(*args, **kw)
        click.echo(f'Time: {stopwatch}', err=True)
        return result
    return wrap

# annotation
def debug_timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        # ts = time.time()
        stopwatch = Stopwatch(2)
        result = f(*args, **kw)
        # te = time.time()
        if logger.isEnabledFor(logging.DEBUG):
            # click.echo(f'⏱ {stopwatch} |> [fn:]{f.__module__}.{f.__name__} | [args:] {args!r} | [kw:] {kw!r}', err=True)
            args = [repr(arg) for arg in args]
            kws = [f"{k}={repr(v)}" for k, v in kw.items()]
            all_args = ', '.join(args + kws)
            click.echo(f'⏱ {stopwatch} |> {f.__module__}.{f.__name__}({all_args})', err=True)
        return result
    return wrap
