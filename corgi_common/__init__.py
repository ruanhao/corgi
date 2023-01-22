import tempfile
import os
import logging
from functools import partial
from logging.handlers import RotatingFileHandler
from hprint import pretty_print
import subprocess
import sys
import signal
import getpass
from contextlib import contextmanager
# from threading import Thread
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import traceback
from icecream import ic, install as install_ic
from datetime import datetime, timezone
from click import echo

logger = logging.getLogger(__name__)
debug = logging.getLogger().getEffectiveLevel() == logging.DEBUG

nbsr_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='nbsr')

tabulate_print = pretty_print   # legecy code

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
            return self._q.get(block=timeout is not None, timeout=timeout)
        except Empty:
            logger.debug(f"NBSR timeout ({timeout}s)")
            return None

    def close(self):
        self._s.close()

def ic_time_format():
    return f'\n{datetime.now()}| '


def install_print_with_flush():
    try:
        builtins = __import__('__builtin__')
    except ImportError:
        builtins = __import__('builtins')

    setattr(builtins, 'print0', print)
    setattr(builtins, 'print', partial(print, flush=True))

def config_logging(name, level=None):
    install_print_with_flush()
    ic.configureOutput(prefix=ic_time_format, includeContext=True)
    ic.disable()
    install_ic()
    # if '-ic' in sys.argv:
    #     ic.enable()
    #     sys.argv.remove('-ic')

    if not level:
        level = logging.INFO
        for option in ('-v', '--verbose', '--debug'):
            if option in sys.argv:
                level = logging.DEBUG
                ic.enable()
                sys.argv.remove(option)
                break
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
    if level == logging.DEBUG:
        import http.client as http_client
        http_client.HTTPConnection.debuglevel = 1
        http_client_logger = logging.getLogger("http.client")

        def __print_to_log(*args):
            # ic(args)
            http_client_logger.debug(" ".join(args))

        http_client.print = __print_to_log


def _chain_get(data, chain, default=None):
    if not chain:
        return data
    attrs = chain.split('.')
    if len(attrs) == 1:
        return data.get(attrs[0], default)
    result = data
    for attr in attrs[:-1]:
        result = result.get(attr, {})
    return result.get(attrs[-1], default)


def get(obj, key, default='n/a'):
    try:
        return _chain_get(obj, key, default)
    except Exception:
        return default


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


def run_script(command, capture=False, realtime=False, opts='', dry=False):
    """When realtime == True, stderr will be redirected to stdout"""
    logger.debug(f"Running subprocess: [{command}] (capture: {capture})")
    if dry:
        print(command)
        return
    preexec_options = {}
    if sys.platform.startswith('win'):
        # https://msdn.microsoft.com/en-us/library/windows/desktop/ms684863(v=vs.85).aspx
        # CREATE_NEW_PROCESS_GROUP=0x00000200 -> If this flag is specified, CTRL+C signals will be disabled
        preexec_options['creationflags'] = 0x00000200
    else:
        preexec_options['preexec_fn'] = lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
    process = subprocess.Popen(
        ['/bin/bash', f'-c{opts}', command],
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
                realtime_output = nbsr.readline(15)  # block 15s at most
                if process.poll() is not None:
                    break
                if realtime_output:
                    logger.debug(f"[{process.pid}:stdout] " + realtime_output.rstrip())
                    echo(realtime_output.rstrip())
                    last_n_lines.append(realtime_output.rstrip())
                    last_n_lines = last_n_lines[-10:]
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
    logger.error(f"See ya [{rc}]: {msg}")
    echo(msg, file=sys.stderr)
    exit(rc)

def goodbye(msg=None):
    logger.info("Bye bye")
    if msg:
        logger.info(f"Bye bye: {msg}")
        echo(msg)
    exit()


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

@contextmanager
def switch_to_tmp_dir():
    orig_cwd = os.getcwd()
    new_cwd = tempfile.mkdtemp()
    logger.info(f"Switching CWD to [{new_cwd}]")
    os.chdir(new_cwd)
    try:
        yield
    finally:
        logger.info(f"Switching CWD BACK to [{orig_cwd}]")
        os.chdir(orig_cwd)

def assert_that(condition_to_fulfill, msg):
    if not condition_to_fulfill:
        traceback.print_stack()
        bye(msg)

def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)
