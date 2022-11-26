import click
from click import echo
from corgi_common import forfun_url
from icecream import ic
from corgi_common.restutils import http_put, http_get, http_post

# _forfun_get = partial(requests.get)
# _forfun_put = partial(requests.put)
# _forfun_post = partial(requests.post)
# _forfun_delete = partial(requests.delete)

def _url(uri):
    url = forfun_url('/redis') + uri
    return ic(url)

@click.group(help='forfun utils [command group]')
def forfun():
    pass


@forfun.command(name='set')
@click.argument('key', required=True)
@click.argument('value', required=True)
def do_set(key, value):
    http_put(
        _url('/set'),
        json={
            'key': ic(key),
            'value': value
        }
    )

@forfun.command(name='pub')
@click.argument('channel', required=True)
@click.argument('data', required=True)
def do_pub(channel, data):
    http_post(
        _url('/pub'),
        json={
            'channel': ic(channel),
            'data': data
        }
    )

@forfun.command(name='get')
@click.argument('key', required=True)
def do_get(key):
    response_data = http_get(
        _url('/get/' + key),
    ).json()
    echo(response_data.get('value'))
