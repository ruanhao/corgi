import click
from .pg_common import execute


@click.group(help="[command group]")
@click.pass_context
def recipes(ctx):
    pass


@recipes.command(short_help='list all sequences in the current database')
@click.pass_context
def sequences(ctx):
    execute(ctx, """
SELECT
    relname sequence_name
FROM
    pg_class
WHERE
    relkind = 'S';
    """)