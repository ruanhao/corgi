import click
import logging
from .dsagent import Agent as DSAgent
from corgi_common import tabulate_print

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@click.group(help="Utils for datastore management")
@click.pass_context
def datastore(ctx):
    pass


@click.command(help="List datastore")
@click.pass_context
def list_dsz(ctx):
    agent = DSAgent.getAgent(**ctx.obj)
    r = agent.list_dsz()
    assert r.ok, r.text
    data = r.json()['value']
    tabulate_print(data, {
        'ID': 'datastore',
        'Name': 'name',
        'Free(GB)': ('free_space', lambda v: int(v / 1024 / 1024 / 1024))
    })


datastore.add_command(list_dsz, "list")
