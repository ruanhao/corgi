import click
import logging
from .dcagent import Agent as DCAgent
from corgi_common import tabulate_print

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@click.group(help="Utils for DC management")
@click.pass_context
def datacenter(ctx):
    pass


@click.command(help="List")
@click.pass_context
def list_dcs(ctx):
    agent = DCAgent.getAgent(**ctx.obj)
    r = agent.list_dcs()
    assert r.ok, r.text
    data = r.json()['value']
    tabulate_print(data, {
        'ID': 'datacenter',
        'Name': 'name',
    })


datacenter.add_command(list_dcs, "list")
