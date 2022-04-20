import tempfile
import os
import logging
from logging.handlers import RotatingFileHandler
from tabulate import tabulate
import subprocess
import sys


logger = logging.getLogger(__name__)


def config_logging(name, level=logging.INFO):
    logging.basicConfig(
        handlers=[
            RotatingFileHandler(
                filename=os.path.join(tempfile.gettempdir(), name) + ".log",
                maxBytes=10 * 1024 * 1024,  # 10M
                backupCount=5),
            # logging.StreamHandler(),  # default to stderr
        ],
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s',
        datefmt='%m/%d/%Y %I:%M:%S %p')


def _chain_get(data, chain, default=None):
    attrs = chain.split('.')
    if len(attrs) == 1:
        return data.get(attrs[0], default)
    result = data
    for attr in attrs[:-1]:
        result = result.get(attr, {})
    return result.get(attrs[-1], default)


def get(obj, key):
    return _chain_get(obj, key, 'N/A')


def tabulate_print(data, mappings):
    headers = mappings.keys()
    tabdata = []
    for item in data:
        attrs = []
        for h in headers:
            k = mappings[h]
            if isinstance(k, tuple):
                (k0, func) = k
                attrs.append(func(get(item, k0)))
            else:
                attrs.append(get(item, k))
        tabdata.append(attrs)
    print(tabulate(tabdata, headers=headers))


def run_script(command, capture=False, realtime=False):
    """When realtime == True, stderr will be redirected to stdout"""
    if 'logger' in globals():
        globals()['logger'].debug(f"Running subprocess: [{command}] (capture: {capture})")
    process = subprocess.Popen(
        ['/bin/bash', '-c', command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if realtime else subprocess.PIPE if capture else subprocess.DEVNULL,
        encoding='utf-8',
        bufsize=1,              # line buffered
    )
    if not realtime:
        stdout, stderr = process.communicate()
        rc = process.returncode
    else:
        stdout, stderr = '', ''
        last_n_lines = []
        while True:
            realtime_output = process.stdout.readline()
            if realtime_output == '' and process.poll() is not None:
                break
            if realtime_output:
                print(realtime_output.rstrip())
                last_n_lines.append(realtime_output.rstrip()); last_n_lines = last_n_lines[-10:]
                sys.stdout.flush()
                if capture:
                    stdout += realtime_output
        rc = process.poll()
        stdout, stderr = stdout.rstrip(), None if realtime else process.stderr.read().rstrip()
    if rc and 'logger' in globals():
        globals()['logger'].critical(f"Subprocess Failed ({rc}): {os.linesep.join(last_n_lines).rstrip() if realtime else stderr}")
    if rc and not capture:
        raise Exception(f"Subprocess Failed ({rc}): {os.linesep.join(last_n_lines).rstrip() if realtime else stderr}")
    return rc, stdout, stderr
