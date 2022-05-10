import tempfile
import os
import logging
from logging.handlers import RotatingFileHandler
from tabulate import tabulate
import subprocess
import sys
import signal
import getpass
from contextlib import contextmanager
# from threading import Thread
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import json
from pprint import pprint

logger = logging.getLogger(__name__)

nbsr_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='nbsr')

class UnexpectedEndOfStream(Exception): pass

class NonBlockingStreamReader:

    def __init__(self, stream):
        '''
        stream: the stream to read from.
                Usually a process' stdout or stderr.
        '''

        self._s = stream
        self._q = Queue()

        def _populateQueue(stream, queue):
            '''
            Collect lines from 'stream' and put them in 'quque'.
            '''

            logger.info("Starting readline ...")
            while True:
                line = stream.readline()
                if line:
                    queue.put(line)
                else:
                    logger.info("Stream EOF")
                    return
                    # raise UnexpectedEndOfStream
        nbsr_executor.submit(_populateQueue, self._s, self._q)
        # self._t = Thread(target=_populateQueue, args=(self._s, self._q))
        # self._t.name = 'nbsr-thread'
        # self._t.daemon = True
        # self._t.start() # start collecting lines from the stream

    def readline(self, timeout=None):
        try:
            return self._q.get(block =timeout is not None, timeout=timeout)
        except Empty:
            logger.debug(f"NBSR timeout ({timeout}s)")
            return None

    def close(self):
        self._s.close()


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


def json_print(data):
    if isinstance(data, dict):
        print(json.dumps(data, indent=4))
    elif isinstance(data, list):
        try:
            print(json.dumps([dict(d) for d in data], indent=4))
        except Exception:
            pprint([dict(d) for d in data])


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


@contextmanager
def switch_cwd(new_cwd):
    orig_cwd = os.getcwd()
    logger.info(f"Switching CWD to [{new_cwd}]")
    os.chdir(new_cwd)
    try:
        yield
    finally:
        logger.info(f"Switching CWD BACK to [{orig_cwd}]")
        os.chdir(orig_cwd)


class NoKeyboardInterrupt:

    def __enter__(self):
        self.signal_received = False
        self.old_handler = signal.signal(signal.SIGINT, self.handler)

    def handler(self, sig, frame):
        # self.signal_received = (sig, frame)
        logging.debug('SIGINT received. Ignoring KeyboardInterrupt.')

    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.old_handler)
        # if self.signal_received:
        #     self.old_handler(*self.signal_received)

def pre_exec():
    # To ignore CTRL+C signal in the new process
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def run_script(command, capture=False, realtime=False):
    """When realtime == True, stderr will be redirected to stdout"""
    logger.debug(f"Running subprocess: [{command}] (capture: {capture})")
    print("$> " + command)
    preexec_options = {}
    if sys.platform.startswith('win'):
        # https://msdn.microsoft.com/en-us/library/windows/desktop/ms684863(v=vs.85).aspx
        # CREATE_NEW_PROCESS_GROUP=0x00000200 -> If this flag is specified, CTRL+C signals will be disabled
        preexec_options['creationflags'] = 0x00000200
    else:
        preexec_options['preexec_fn'] = lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
    process = subprocess.Popen(
        ['/bin/bash', '-c', command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if realtime else subprocess.PIPE if capture else subprocess.DEVNULL,
        encoding='utf-8',
        bufsize=1,              # line buffered
        **preexec_options,
    )
    nbsr = None
    try:
        if not realtime:
            stdout, stderr = process.communicate()
            rc = process.returncode
        else:
            stdout, stderr = '', ''
            last_n_lines = []
            nbsr = NonBlockingStreamReader(process.stdout)
            while True:
                realtime_output = nbsr.readline(15) # block 15s at most
                if process.poll() is not None:
                    break
                if realtime_output:
                    logger.debug(f"[{process.pid}:stdout] " + realtime_output.rstrip())
                    print(realtime_output.rstrip())
                    last_n_lines.append(realtime_output.rstrip()); last_n_lines = last_n_lines[-10:]
                    sys.stdout.flush()
                    if capture:
                        stdout += realtime_output
            rc = process.poll()
            stdout, stderr = stdout.rstrip(), None if realtime else process.stderr.read().rstrip()
        if rc:
            logger.critical(f"Subprocess Failed ({rc}): {os.linesep.join(last_n_lines).rstrip() if realtime else stderr}")
        if rc and not capture:
            raise Exception(f"Subprocess Failed ({rc}): {os.linesep.join(last_n_lines).rstrip() if realtime else stderr}")
        return rc, stdout, stderr
    except KeyboardInterrupt:
        logger.info("Sending SIGINT to subprocess ..")
        process.send_signal(signal.SIGINT)
        logger.info("Waiting subprocess to exit gracefully..")
        with NoKeyboardInterrupt():
            process.wait()
    finally:
        if nbsr:
            nbsr.close()

# annotation
def as_root(func):
    def inner_function(*args, **kwargs):
        if not is_root():
            bye("Please run as root.")
        func(*args, **kwargs)
    return inner_function

def is_root():
    return getpass.getuser() == 'root'

def bye(msg, rc=1):
    print(msg, file=sys.stderr)
    exit(rc)
