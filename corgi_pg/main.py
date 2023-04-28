#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import time
from corgi_common.loggingutils import config_logging
from corgi_common.scriptutils import pause
from .tutorial import tutorial
from .recipes import recipes
from .demo import demo
from .index import index
from .internals import internals
from .pg_common import execute as e, pg_cursor, psql, get_show_result, get_share_conn, reload_conf, create_connection
import logging
import sys
from corgi_common.timeutils import simple_timing
from corgi_common.dateutils import YmdHMS
from hprint import hprint
from os.path import join, exists
from psycopg2.extensions import (
    ISOLATION_LEVEL_AUTOCOMMIT,
    ISOLATION_LEVEL_READ_COMMITTED,
    # ISOLATION_LEVEL_READ_UNCOMMITTED,
    ISOLATION_LEVEL_REPEATABLE_READ,
    ISOLATION_LEVEL_SERIALIZABLE
)

logger = logging.getLogger(__name__)

@click.group(help="CLI tool for Postgres")
@click.pass_context
@click.option('--hostname', envvar='PGHOST', show_default=True, required=True)
@click.option('--port', envvar='PGPORT', default=5672, type=int)
@click.option('--user', envvar='PGUSER', required=True)
@click.option('--database', envvar='PGDATABASE', default='dvdrental')
@click.option('--password', '-p', envvar='PGPASSWORD')
@click.option(
    '--isolation-level', '-i', envvar='CORGI_PG_ISOLATION_LEVEL', type=int,
    default=ISOLATION_LEVEL_READ_COMMITTED,
    help='auto:0, rc:1, rr:2, s:3'
)
@click.option('--json', '-json', 'as_json', is_flag=True)
@click.option('--dry', is_flag=True)
@click.option('-x', is_flag=True)
def cli(ctx, hostname, port, user, password, database, as_json, x, dry, isolation_level):
    ctx.ensure_object(dict)
    ctx.obj['user'] = user
    ctx.obj['password'] = password
    ctx.obj['database'] = database
    ctx.obj['host'] = hostname
    ctx.obj['port'] = port
    ctx.obj['as_json'] = as_json
    ctx.obj['x'] = x
    ctx.obj['dry'] = dry
    ctx.obj['isolation_level'] = isolation_level
    pass

# @cli.command(short_help='show data directory')
# @click.pass_context
# def data_dir(ctx):
#     e(ctx, "show data_directory;")

@cli.command(short_help='show dir path for table')
@click.pass_context
@click.argument('tbl')
def table_path(ctx, tbl):
    ctx.obj['as_json'] = True
    filepath = e(ctx, f"SELECT pg_relation_filepath('{tbl}');", raw=True)[0]['pg_relation_filepath']
    data_dir = get_show_result(ctx, 'data_directory')
    abs_path = join(data_dir, filepath)
    size = e(ctx, f"SELECT size FROM pg_stat_file('{abs_path}');", raw=True)[0]['size']
    result = []
    result.append({'path': filepath, 'size': size})
    for i in range(1, 100):
        filepath0 = filepath + "." + str(i)
        abs_path0 = join(data_dir, filepath0)
        if not exists(abs_path0):
            break
        size0 = e(ctx, f"SELECT size FROM pg_stat_file('{abs_path0}');", raw=True)[0]['size']
        result.append({'path': filepath0, 'size': size0})
    hprint(result)

@cli.command(short_help='show numbers of all pages and all tuples the table')
@click.pass_context
@click.argument('tbl')
def table_pages_and_tuples(ctx, tbl):
    e(ctx, f"ANALYZE {tbl};")
    e(ctx, f"""SELECT relpages, reltuples, (reltuples / relpages)::int AS "avg tuples/page" FROM pg_class WHERE relname = '{tbl}';""")

@cli.command(short_help='show column storage type')
@click.pass_context
@click.argument("tbl")
def table_column_storage(ctx, tbl):
    """\b
Workflow:

1. First of all, go through attributes with external and extended strategies, starting from the longest ones.
   Extended attributes get compressed, and if the resulting value (on its own, without taking other attributes into account) exceeds one fourth of the page, it is moved to the TOAST table right away.
   External attributes are handled in the same way, except that the compression stage is skipped.

2. If the row still does not fit the page after the first pass, move the remaining attributes that use external or extended strategies into the TOAST table, one by one.

3. If it did not help either, we try to compress the attributes that use the main strategy, keeping them in the table page.

4. If the row is still not short enough, the main attributes are moved into the TOAST table.
    """

    e(ctx, f"""
SELECT attname, atttypid::regtype,
  CASE attstorage
    WHEN 'p' THEN 'plain'
    WHEN 'e' THEN 'external'
    WHEN 'm' THEN 'main'
    WHEN 'x' THEN 'extended'
  END AS storage
FROM pg_attribute
WHERE attrelid = '{tbl}'::regclass AND attnum > 0;
    """)

    result = e(ctx, f"""
SELECT relnamespace::regnamespace, relname FROM pg_class
WHERE oid = (
SELECT reltoastrelid
FROM pg_class WHERE relname = '{tbl}' );
    """, desc=f'corresponding TOAST table', raw=True, as_json=True)
    if result:
        toast_table = result[0]['relname']
        psql(ctx, '\d+ pg_toast.' + toast_table, desc="descript TOAST table")
        e(ctx, f"""
SELECT chunk_id,
       chunk_seq,
       length(chunk_data),
       left(encode(chunk_data,'escape')::text, 10) || '...' || right(encode(chunk_data,'escape')::text, 10)
FROM pg_toast.{toast_table};
        """, desc='show TOAST table')
    pass

@cli.command(short_help='show basic info')
@click.pass_context
def info(ctx):
    print("connection info(dsn):", create_connection(ctx).dsn)
    print()
    keys = [
        ('server_version', lambda v: v.split()[0]),
        ('data_directory', None),
        ('transaction_isolation', None),
    ]
    # version = get_show_result(ctx, 'server_version', lambda v: v.split()[0])
    # data_dir = get_show_result(ctx, 'data_directory')
    result = {}
    for key, extractor in keys:
        value = get_show_result(ctx, key, extractor)
        result[key] = value
    hprint([result], x=True)


@cli.command(short_help='show current walfile')
@click.pass_context
def walfile(ctx):
    e(ctx, """select pg_walfile_name(pg_current_wal_lsn());""")

@cli.command(short_help='switch walfile')
@click.pass_context
def walfile_switch(ctx):
    e(ctx, """select pg_switch_wal();""")

@cli.command(short_help='create restore point')
@click.pass_context
@click.argument("name", required=False)
def create_restore_point(ctx, name):
    """\b
    restore by setting 'recovery_target_name = <name>' in postgresql.conf

    do it before issueing critical operations
    """
    if not name:
        name = 'my-checkpoint-' + YmdHMS()
    print(f"checkpoint: {name}")
    e(ctx, f"""select pg_create_restore_point('{name}');""")


@cli.command(short_help='show procedures')
@click.pass_context
@click.option('--regex', '-r', default='.*', show_default=True)
@click.option('--definition/--no-definition')
@click.option('--args/--no-args')
def procedures(ctx, regex, definition, args):
    sql = f"""
SELECT
    n.nspname AS schema,
    proname AS procedure,
    {"proargnames AS args," if args else ""}
    t.typname AS return_type,
    TRIM(d.description) AS desc
    {",pg_get_functiondef(p.oid) as definition" if definition else ""}
FROM pg_proc p
JOIN pg_type t ON p.prorettype = t.oid
LEFT OUTER JOIN pg_description d ON p.oid = d.objoid
LEFT OUTER JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE proname~'^.*{regex}.*$';
    """
    if definition or args:
        ctx.obj['x'] = True
    e(ctx, sql)
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
    """\b
- public
  the default schema for user objects unless other settings are specified.
- pg_catalog
  used for system catalog tables.
- information_schema
  provides an alternative view for the system catalogas defined by the SQL standard.
- pg_toast
  used for objects related to TOAST.
- pg_temp
  comprises temporary tables. Although different users create temporary tables in different schemas called pg_temp_N, everyone refers to their objects using the pg_temp alias.
    """
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
    tablespaces define physical data layout.

    'pg_default' tablespace stores user data which is located in the PGDATA/base directory.
    'pg_global'  tablespace stores global data (system catalog objects) which is located in the PGDATA/global directory.
    """
    psql(ctx, '\db+')

@cli.command()
@click.pass_context
@click.option('--public', '-p', is_flag=True)
@click.option('--system', '-s', is_flag=True)
def tables(ctx, public, system):
    where = ''
    if public:
        where = "WHERE schemaname = 'public'"
    if system:
        where = "WHERE schemaname = 'pg_catalog'"
    sql = "SELECT schemaname, tablename, tableowner FROM pg_catalog.pg_tables " + where
    e(ctx, sql)

@cli.command(short_help="describe table")
@click.pass_context
@click.argument('tbl_name')
def table_describe(ctx, tbl_name):
    psql(ctx, f"\d {tbl_name}")

@cli.command(short_help="show table indexes")
@click.pass_context
@click.option('--table', '-t', help='table name')
def indexes(ctx, table):
    if not table:
        e(ctx, """
select
    t.relname as table_name,
    i.relname as index_name,
    a.attname as column_name
from
    pg_class t,
    pg_class i,
    pg_index ix,
    pg_attribute a
where
    t.oid = ix.indrelid
    and i.oid = ix.indexrelid
    and a.attrelid = t.oid
    and a.attnum = ANY(ix.indkey)
    and t.relkind = 'r'
   -- and t.relname like 'mytable'
order by
    t.relname,
    i.relname;
        """)
        return
    e(ctx, f"""
SELECT
    indexname,
    indexdef
FROM
    pg_indexes
WHERE
    tablename = '{table}';
    """)

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

@cli.command(short_help='setup log_statement')
@click.pass_context
@click.option('--none', is_flag=True, help="set to 'none'")
@click.option('--ddl', is_flag=True, help="set to 'ddl'")
@click.option('--mod', is_flag=True, help="set to 'mod'")
def log_statement(ctx, none, ddl, mod):
    if none:
        value = 'none'
    elif ddl:
        value = 'ddl'
    elif mod:
        value = 'mod'
    else:
        value = 'all'
    e(ctx, f"ALTER SYSTEM SET log_statement = '{value}';", isolation_level=ISOLATION_LEVEL_AUTOCOMMIT)
    reload_conf(ctx)

@cli.command(short_help='rebuild all indices in table')
@click.pass_context
@click.argument('tbl_name')
@simple_timing
def reindex_table(ctx, tbl_name):
    """\b
The REINDEX statement rebuilds the index contents from the scratch, which has a similar effect as dropping and recreate of the index.
However, the locking mechanisms between them are different.

- The REINDEX statement:

  Locks writes but not reads from the table to which the index belongs.
  Takes an exclusive lock on the index that is being processed, which blocks read that attempts to use the index.

- The DROP INDEX & CREATE INDEX statements:

  First, the DROP INDEX locks both writes and reads of the table to which the index belongs by acquiring an exclusive lock on the table.
  Then, the subsequent CREATE INDEX statement locks out writes but not reads from the index's parent table. However, reads might be expensive during the creation of the index.

See https://www.postgresqltutorial.com/postgresql-indexes/postgresql-reindex/
"""
    e(ctx, f"REINDEX TABLE {tbl_name};")

@cli.command(hidden=True)
@click.pass_context
def test(ctx):
    # ic(ISOLATION_LEVEL_AUTOCOMMIT)
    # ic(ISOLATION_LEVEL_READ_COMMITTED)
    # ic(ISOLATION_LEVEL_REPEATABLE_READ)
    # ic(ISOLATION_LEVEL_SERIALIZABLE)

    e(ctx, """
DROP TABLE IF EXISTS hot;
CREATE TABLE hot (id int PRIMARY KEY, data text);
CREATE INDEX hot_data_idx ON hot (data);
-- INSERT INTO tbl SELECT generate_series(1,10000),generate_series(1,10000);
INSERT INTO hot(id, data) values (1, 'a');
ANALYZE;
    """)



@cli.command(short_help="execute SQL ad-hoc", name='execute')
@click.pass_context
@click.argument('statement', required=False)
def run(ctx, statement):
    # execute(ctx, "select version();")
    # execute(ctx, "SELECT first_name FROM customer;")
    # execute(ctx, "SELECT * FROM customer;")
    # execute(ctx, "SELECT * FROM rental LIMIT 5;")
    if statement:
        e(ctx, statement)
    else:
        e(ctx)
#    print("test")

@cli.command(short_help='show query plan')
@click.pass_context
@click.option('--buffers/--no-buffers')
@click.argument('statement', required=False)
def explain(ctx, statement, buffers):
    """\b
See:
  - https://medium.com/geekculture/how-to-read-postgresql-query-plan-df4b158781a1
    """
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


def _recursive_help(cmd, parent=None, indent=0, include_hidden=False):
    ctx = click.core.Context(cmd, info_name=cmd.name, parent=parent)
    if (not cmd.hidden) or include_hidden:
        print(" " * indent, cmd.get_help(ctx).splitlines()[0])
    commands = getattr(cmd, 'commands', {})
    for sub in commands.values():
        _recursive_help(sub, ctx, indent=indent + 2, include_hidden=include_hidden)


@cli.command(name='help', help='dump help for all commands')
@click.option('--all', '-a', 'include_hidden', is_flag=True)
def dumphelp(include_hidden):
    _recursive_help(cli, include_hidden=include_hidden)

cli.add_command(tutorial)
cli.add_command(recipes)
cli.add_command(index)
cli.add_command(internals)
cli.add_command(demo)

def main():
    config_logging('corgi_pg')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
