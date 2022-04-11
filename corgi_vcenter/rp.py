import click
import logging
from .rpagent import Agent as RPAgent
from corgi_common import tabulate_print

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@click.group(help="Utils for resource pool management")
@click.pass_context
def resource_pool(ctx):
    pass


@click.command(help="List resource pool")
@click.option('--hosts', '-h', required=False, help='Hosts')
@click.pass_context
def list_rps(ctx, hosts):
    agent = RPAgent.getAgent(**ctx.obj)
    r = agent.list_resource_pools(hosts=hosts)
    assert r.ok, r.text
    data = r.json()['value']
    # print(data)
    tabulate_print(data, {
        'ID': 'resource_pool',
        'Name': 'name',
    })


resource_pool.add_command(list_rps, "list")
