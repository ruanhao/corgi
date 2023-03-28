import click
from .pg_common import execute, psql
from corgi_common.scriptutils import run_script


@click.group(help="[command group]")
@click.pass_context
def recipes(ctx):
    pass


@recipes.command(short_help='list all sequences in the current database')
@click.pass_context
@click.option('--limit', '-n', type=int, default=5)
def biggest_tables(ctx, limit):
    execute(ctx, f"""
SELECT
    relname AS "relation",
    pg_size_pretty (
        pg_total_relation_size (C .oid)
    ) AS "total_size",
    pg_size_pretty (
        pg_indexes_size (C .oid)
    ) AS "index_size"
FROM
    pg_class C
LEFT JOIN pg_namespace N ON (N.oid = C .relnamespace)
WHERE
    nspname NOT IN (
        'pg_catalog',
        'information_schema'
    )
AND C .relkind <> 'i'
AND nspname !~ '^pg_toast'
ORDER BY
    pg_total_relation_size (C .oid) DESC
LIMIT {limit};
    """)

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

@recipes.command(short_help='show type with len')
@click.pass_context
def types(ctx):
    execute(ctx, """
SELECT
    typname,
    typlen
FROM
    pg_type;
    """)

@recipes.command(short_help='see the current pending transactions that are on-going')
@click.pass_context
@click.option("--database", '-db', envvar='CORGI_PG_DATABASE', required=True)
def terminate_conns(ctx, database):
    execute(ctx, f"""
SELECT
    datname AS database,
    application_name,
    username,
    pid,
    client_addr || ':' || client_port AS client,
    pg_terminate_backend (pg_stat_activity.pid)
FROM
    pg_stat_activity
WHERE
    pg_stat_activity.datname = '{database}';
    """)

@recipes.command(short_help='dump table schema')
@click.pass_context
@click.argument("table", required=True)
def table_schema_dump(ctx, table):
    command = f"pg_dump -h {ctx.obj['host']} -p {ctx.obj['port']} -U {ctx.obj['user']} -d {ctx.obj['database']}"
    if ctx.obj['password']:
        command += f" -W {ctx.obj['password']}"
    command += f" --table {table} --schema-only"
    rc, stdout, stderr = run_script(command)
    print(stdout)
