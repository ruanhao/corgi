import click
import logging
from .hostagent import Agent as HostAgent
from corgi_common import tabulate_print

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@click.group(help="Utils for Host management")
@click.pass_context
def host(ctx):
    pass


@click.command(help="List Host")
@click.pass_context
def list_hosts(ctx):
    agent = HostAgent.getAgent(**ctx.obj)
    r = agent.list_hosts()
    assert r.ok, r.text
    data = r.json()['value']
    tabulate_print(data, {
        'Host': 'host',
        'Name': 'name',
        'Conn_State': 'connection_state',
        'Power': 'power_state',

    })


host.add_command(list_hosts, "list")
