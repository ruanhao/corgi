import requests
from contextlib import redirect_stdout
import sys
from functools import partial
from click import echo
from corgi_common import json_print

def _check_response(r):
    if r.ok:
        return
    with redirect_stdout(sys.stderr):
        try:
            json_print(r.json())
        except Exception:
            echo(r.text)
        r.raise_for_status()

def _http_method(url, method, *args, **kwargs):
    assert method in ['get', 'post', 'delete', 'put']
    response = getattr(requests, method)(url, *args, **kwargs)
    _check_response(response)
    return response


http_get = partial(_http_method, method='get')
http_post = partial(_http_method, method='post')
http_put = partial(_http_method, method='put')
http_delete = partial(_http_method, method='delete')
