import requests
import logging
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import os
import functools
import pickle
import tempfile

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)

SESSION_INFO_FILE = os.path.join(tempfile.gettempdir(), "vc.session.info")


def no_empty_args(f):
    """Annotation for non empty args check."""
    def func(*args, **kwargs):
        if any(arg is None or arg == '' for arg in args):
            raise ValueError('function {}: should not take empty arguments'.format(f.__name__))
        return f(*args, **kwargs)
    return func


def authenticate(host, username, password) -> requests.Session:
    url = "https://{}/rest/com/vmware/cis/session".format(host)
    session = requests.Session()
    session.verify = False
    logger.info("Creating VC session ...")
    r = session.post(url, auth=(username, password))
    if not r.ok:
        logger.error("Failed to get session from {}:{}".format(url, r.text))
        r.raise_for_status()
    token = r.json()['value']
    logger.info(f"Token for VC session: {token}")
    session.headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'vmware-api-session-id': token,
    }
    logger.info(f"Got session: {session}")
    return session


def refreshable(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        r = func(self, *args, **kwargs)
        if r.status_code == 401:
            logger.warn("Session outdated, refreshing ...")
            try:
                self.session = authenticate(self.host, self.username, self.password)
                with open(SESSION_INFO_FILE, 'wb') as f:
                    pickle.dump(self.session, f)
            except Exception as e:
                logger.error(f"Failed to refresh session: {e}")
            return func(self, *args, **kwargs)
        return r
    return wrapper


class RefreshableSession:

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        if os.path.isfile(SESSION_INFO_FILE):
            logger.debug(f"Loading session info from {SESSION_INFO_FILE} ...")
            with open(SESSION_INFO_FILE, 'rb') as f:
                self.session = pickle.load(f)
                self.session.verify = False
        else:
            self.session = authenticate(host, username, password)
            with open(SESSION_INFO_FILE, 'wb') as f:
                pickle.dump(self.session, f)

    @refreshable
    def get(self, *args, **kwargs):
        return self.session.get(*args, **kwargs)

    @refreshable
    def post(self, *args, **kwargs):
        return self.session.post(*args, **kwargs)

    @refreshable
    def put(self, *args, **kwargs):
        return self.session.put(*args, **kwargs)

    @refreshable
    def delete(self, *args, **kwargs):
        return self.session.delete(*args, **kwargs)

    @refreshable
    def patch(self, *args, **kwargs):
        return self.session.patch(*args, **kwargs)


class VCRestAgent:

    @classmethod
    @no_empty_args
    def getAgent(cls, url, username, password):
        if hasattr(cls, 'agent'):
            return cls.agent
        cls.agent = cls()
        cls.agent.host = url
        cls.agent.session = RefreshableSession(cls.agent.host, username, password)
        return cls.agent

    def get(self, url, params={}, headers={}):
        return self.session.get(url, params=params, headers=headers)

    def patch(self, url, params={}, payload={}, headers={}):
        return self.session.patch(url, params=params, json=payload, headers=headers)

    def post(self, url, params={}, payload={}, headers={}):
        return self.session.post(url, params=params, json=payload, headers=headers)

    def put(self, url, params={}, payload={}, headers={}):
        return self.session.put(url, params=params, json=payload, headers=headers)

    def delete(self, url, params={}, headers={}, payload={}):
        return self.session.delete(url, params=params, headers=headers, json=payload)
