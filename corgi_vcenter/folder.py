import click
import logging
from .folderagent import Agent as FolderAgent
from corgi_common import tabulate_print

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@click.group(help="Utils for Folder management")
@click.pass_context
def folder(ctx):
    pass


@click.command(help="List Folder")
@click.option('--names', '-n', required=False, help="Specify folder names")
@click.pass_context
def list_folders(ctx, names):
    agent = FolderAgent.getAgent(**ctx.obj)
    r = agent.list_folders(names=names)
    assert r.ok, r.text
    data = r.json()['value']
    tabulate_print(data, {
        'ID': 'folder',
        'Name': 'name',
        'Type': 'type',
    })


folder.add_command(list_folders, "list")
