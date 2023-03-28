#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common.loggingutils import config_logging
from .tutorial import tutorial
from .recipes import recipes
from .pg_common import execute as e, pg_cursor, psql
import logging
import sys

logger = logging.getLogger(__name__)

@click.group(help="CLI tool for Postgres")
@click.pass_context
@click.option('--hostname', envvar='CORGI_PG_HOST', show_default=True, required=True)
@click.option('--port', envvar='CORGI_PG_PORT', default=5672, type=int)
@click.option('--user', envvar='CORGI_PG_USER', required=True)
@click.option('--database', envvar='CORGI_PG_DATABASE', default='dvdrental')
@click.option('--password', '-p', envvar='CORGI_PG_PASSWORD')
@click.option('--json', '-json', 'as_json', is_flag=True)
@click.option('-x', is_flag=True)
def cli(ctx, hostname, port, user, password, database, as_json, x):
    ctx.ensure_object(dict)
    ctx.obj['user'] = user
    ctx.obj['password'] = password
    ctx.obj['database'] = database
    ctx.obj['host'] = hostname
    ctx.obj['port'] = port
    ctx.obj['as_json'] = as_json
    ctx.obj['x'] = x
    pass

@cli.command(short_help='see the current pending transactions that are on-going')
@click.pass_context
def activities(ctx):
    """\b
    You should look at the result to find the state column with the value  'idle in transaction'.
    Those are the transactions that are pending to complete.
    """
    ctx.obj['x'] = True
    e(ctx, f"""
SELECT
    *
--    datid,
--    datname,
--    usename,
--    state
FROM
    pg_stat_activity
WHERE
    datname = '{ctx.obj['database']}';
    """)

@cli.command(short_help='all schemas from the current database')
@click.pass_context
@click.option("--user", '-u', is_flag=True, help='')
def schemas(ctx, user):
    where = ""
    if user:
        where = """WHERE nspacl is NULL AND nspname NOT LIKE 'pg_%'"""
    e(ctx, f"""
SELECT n.oid, n.nspname, n.nspowner, r.rolname AS nspowner_name, n.nspacl
FROM pg_catalog.pg_namespace AS n
JOIN pg_roles as r ON n.nspowner = r.oid
{where}
ORDER BY nspname;
    """)

@cli.command(short_help='show roles')
@click.pass_context
def roles(ctx):
    psql(ctx, "\du+")
#     e(ctx, """
# SELECT usename AS role_name,
#   CASE
#      WHEN usesuper AND usecreatedb THEN
#        CAST('superuser, create database' AS pg_catalog.text)
#      WHEN usesuper THEN
#         CAST('superuser' AS pg_catalog.text)
#      WHEN usecreatedb THEN
#         CAST('create database' AS pg_catalog.text)
#      ELSE
#         CAST('' AS pg_catalog.text)
#   END role_attributes
# FROM pg_catalog.pg_user
# ORDER BY role_name desc;
#     """)

@cli.command(short_help='show table spaces info')
@click.pass_context
def tablespaces(ctx):
    """\b
    'pg_default' tablespace stores user data.
    'pg_global'  tablespace stores global data.
    """
    psql(ctx, '\db+')

@cli.command()
@click.pass_context
def tables(ctx):
    e(ctx, """SELECT schemaname, tablename, tableowner FROM pg_catalog.pg_tables WHERE schemaname = 'public';""")

@cli.command(short_help="describe table")
@click.pass_context
@click.argument('tbl_name')
def table_describe(ctx, tbl_name):
    psql(ctx, f"\d {tbl_name}")

@cli.command(short_help="Grant all privileges on all tables in public schema to a role")
@click.pass_context
@click.argument('role')
def grant_all_tables_to(ctx, role):
    """
    GRANT is used to grant privileges on database objects to a role.
    """
    e(ctx, f"""
GRANT ALL
ON ALL TABLES
IN SCHEMA "public"
TO {role};
    """)

@cli.command(short_help='create role')
@click.pass_context
@click.argument('name')
@click.option("--pass", '-p', "password", required=True)
def role_create(ctx, name, password):
    """\b
    Typically, roles can log in are called 'login roles'. They are equivalent to users in other database systems.
    When roles contain other roles, they are call 'group roles'.

    Notice that you must be a superuser in order to create another superuser role.
    """
    e(ctx, f"""
CREATE ROLE {name}
SUPERUSER
LOGIN
PASSWORD '{password}';
    """)
    pass

@cli.command()
@click.pass_context
@click.option('--buffers/--no-buffers')
@click.argument('statement', required=False)
def explain(ctx, statement, buffers):
    if not statement:
        statement = sys.stdin.read()
    print(50 * '-')
    verbose = logger.isEnabledFor(logging.DEBUG)
    with pg_cursor(**ctx.obj) as cur:
        try:
            cur.execute(f"""
            EXPLAIN (ANALYZE TRUE, BUFFERS {"TRUE" if buffers else "FALSE"}, VERBOSE {"TRUE" if verbose else "FALSE"})
            {statement};
            """)
            rows = cur.fetchall()
            for row in rows:
                print(row['QUERY PLAN'])
        finally:
            cur.connection.rollback()

cli.add_command(tutorial)
cli.add_command(recipes)

def main():
    config_logging('corgi_pg')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
