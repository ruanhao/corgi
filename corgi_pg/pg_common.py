import logging
from datetime import datetime
import os
import psycopg2
import click
import sys
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import (
    ISOLATION_LEVEL_AUTOCOMMIT,
    ISOLATION_LEVEL_READ_COMMITTED,
    # ISOLATION_LEVEL_READ_UNCOMMITTED,
    ISOLATION_LEVEL_REPEATABLE_READ,
    ISOLATION_LEVEL_SERIALIZABLE
)
from hprint import hprint as pprint
from corgi_common.scriptutils import run_script
# from corgi_common.timeutils import simple_timing
# from collections import OrderedDict

logger = logging.getLogger(__name__)

_pg_conn = None

_iso_names = {
    ISOLATION_LEVEL_AUTOCOMMIT: 'auto_commit',
    ISOLATION_LEVEL_READ_COMMITTED: 'read_committed',
    ISOLATION_LEVEL_REPEATABLE_READ: 'repeatable_read',
    ISOLATION_LEVEL_SERIALIZABLE: 'serializable'
}

_pg_conns = {
    ISOLATION_LEVEL_AUTOCOMMIT: None,
    ISOLATION_LEVEL_READ_COMMITTED: None,
    ISOLATION_LEVEL_REPEATABLE_READ: None,
    ISOLATION_LEVEL_SERIALIZABLE: None
}

def get_share_conn(isolation_level):
    return _pg_conns[isolation_level]

def fatal(msg):
    click.secho(msg, bg='black', fg='red', bold=True, err=True)
    logger.critical(msg)
    sys.exit(1)

def debug(s, logger=logger):
    if logger.isEnabledFor(logging.DEBUG):
        print(f'{datetime.now()}|> {s}')
    logger.debug(s)

def _set_connection_readonly(connection, readonly=None):
    if connection.readonly == readonly:
        return
    logger.debug(f"setting readonly as {readonly}, connection:{connection}")
    connection.readonly = readonly

def _set_connection_deferrable(connection, deferrable=None):
    if connection.deferrable == deferrable:
        return
    logger.debug(f"setting deferrable as {deferrable}, connection:{connection}")
    connection.deferrable = deferrable

def _set_connection_isolation_level(connection, isolation_level):
    isolation_level_name = _iso_names[isolation_level]
    logger.debug(f"setting isolation level as {isolation_level_name}({isolation_level}), connection:{connection}")
    connection.set_isolation_level(isolation_level);
    return connection

def _show_connection_info(conn):
    logger.info(f"backend pid: {conn.get_backend_pid()}, connection:{conn}")
    ic(conn.readonly)
    ic(conn.deferrable)
    ic(conn.status)
    pass

def _get_pg_conn(
        host=os.getenv("PGHOST"),
        port=45432,
        database='cbd', user='cbd', password=None,
        share_conn=True,
        readonly=None,
        deferrable=None,
        isolation_level=ISOLATION_LEVEL_READ_COMMITTED,
        **kwargs
):
    global _pg_conns

    if share_conn and _pg_conns[isolation_level]:
        ic(isolation_level)
        sc = _pg_conns[isolation_level]
        iso = sc.isolation_level
        ic(iso)
        iso_name = _iso_names[iso]
        logger.debug(f"[connection reused] {sc} [isolation:{iso_name}({iso})]")
        _set_connection_readonly(sc, readonly)
        _set_connection_deferrable(sc, deferrable)
        return sc

    try:
        with psycopg2.connect(host=host, port=port, database=database, user=user, password=password) as conn:
            logger.debug(f"[connection created] [postgres://{user}@{host}:{port})/{database}] server version: {conn.server_version}, protocol version: {conn.protocol_version}")
            _set_connection_isolation_level(conn, isolation_level)
            _set_connection_readonly(conn, readonly)
            _set_connection_deferrable(conn, deferrable)
            _show_connection_info(conn)
            if share_conn:
                _pg_conns[isolation_level] = conn
                logger.debug(f"connection cached: {_pg_conns}")
            return conn
    except psycopg2.DatabaseError as e:
        fatal(f"failed to connect to postgres: {e}")

def create_connection(ctx, isolation_level=ISOLATION_LEVEL_READ_COMMITTED):
    return _get_pg_conn(
        host=ctx.obj['host'],
        port=ctx.obj['port'],
        database=ctx.obj['database'],
        user=ctx.obj['user'],
        password=ctx.obj['password'],
        share_conn=False,
        isolation_level=isolation_level
    )


# def pg_cursor(host=None, port=45432, database='cbd', user='cbd', password=None, dict_like=True):
def pg_cursor(host=None, dict_like=True, connection=None, **kwargs):
    cursor = (connection or _get_pg_conn(host=host, **kwargs))\
        .cursor(cursor_factory=(RealDictCursor if dict_like else None))
    execute0 = cursor.execute

    def _execute(query, **kwargs):
        if not query.strip().endswith(';'):
            query += ';'
        logger.info(f"""SQL statement ({cursor.connection.get_backend_pid()}):
****************** SQL ************************
{query}
**********************************************""")
        # logger.info(f"[{cursor.connection.get_backend_pid()}] statement |> {query}")
        return execute0(query, **kwargs)

    cursor.execute = _execute
    return cursor


def pg_execute(statement, *args, commit=True, **kwargs):
    with pg_cursor(*args, **kwargs) as cur:
        try:
            cur.execute(statement)
            if commit:
                cur.connection.commit()
            rows = cur.fetchall()
            return [dict(row) for row in rows]
        except (Exception, psycopg2.DatabaseError) as error:
            if 'no results to fetch' == str(error):
                if logger.isEnabledFor(logging.DEBUG):
                    click.secho(error, fg='yellow', err=True)
                return
            click.secho(error, fg='red', err=True)
            cur.connection.rollback()

# def pg_query(statement, *args, **kwargs):
#     with pg_cursor(*args, **kwargs) as cur:
#         try:
#             cur.execute(statement)
#             rows = cur.fetchall()
#             cur.connection.commit()
#             result = []
#             for row in rows:
#                 result.append(dict(row))
#                 # result.append(OrderedDict(row))
#             return result
#         except (Exception, psycopg2.DatabaseError) as error:
#             click.secho(error, fg='red', err=True)
#             cur.connection.rollback()

null = click.style("[null]", fg='bright_black')

def execute(
        ctx, statement='',
        raw=False, desc='', as_json=False, x=False, missing_value=null,
        isolation_level=None,
        share_conn=True, commit=True,
        readonly=None, deferrable=None,
        connection=None,
):
    if not statement:
        statement = sys.stdin.read()
    statement = statement.strip()
    # if not statement.lower().startswith('select'):
    if desc and not raw:
        click.secho(desc + ' ->', underline=True)
    if ctx.obj.get('dry'):
        print(statement)
        return
    isolation_level0 = ctx.obj['isolation_level']
    try:
        if isolation_level:
            ctx.obj['isolation_level'] = isolation_level
        return pprint(
            pg_execute(statement, share_conn=share_conn, commit=commit, readonly=readonly, deferrable=deferrable, connection=connection, **ctx.obj),
            as_json=as_json or ctx.obj['as_json'],
            x=x or ctx.obj['x'],
            missing_value=missing_value,
            raw=raw
        )
    finally:
        ctx.obj['isolation_level'] = isolation_level0

def select_all(ctx, table_name):
    execute(ctx, f"SELECT * FROM {table_name};")

def psql(ctx, command, desc=''):
    _rc, stdout, _stderr = \
        run_script(f"psql postgresql://{ctx.obj['user']}:@{ctx.obj['host']}:{ctx.obj['port']}/{ctx.obj['database']}  -c '{command};'")
    if desc:
        click.secho(desc + ' ->', underline=True)
    print(stdout.strip())

def explain(ctx, statement, buffers=False, verbose=False, costs=True):
    explain_str = f"""
EXPLAIN (
    ANALYZE ,
    BUFFERS {"" if buffers else "FALSE"},
    COSTS {"" if costs else "off"},
    VERBOSE {"" if verbose else "FALSE"}
)
{statement};
"""
    if ctx.obj['dry']:
        print(explain_str)
        return
    with pg_cursor(**ctx.obj) as cur:
        try:
            cur.execute(explain_str)
            rows = cur.fetchall()
            for row in rows:
                print(row['QUERY PLAN'])
        finally:
            cur.connection.rollback()

def get_show_result(ctx, key, extractor=None):
    as_json0 = ctx.obj['as_json']
    try:
        ctx.obj['as_json'] = True
        result = execute(ctx, f"SHOW {key};", raw=True)
        value = result[0][key]
        return (extractor or (lambda value: value))(value)
    finally:
        ctx.obj['as_json'] = as_json0

def create_extension(ctx, extension):
    execute(ctx, f"CREATE EXTENSION IF NOT EXISTS {extension};")

def t_describe(ctx, tbl):
    psql(ctx, "\d " + tbl)
