import logging
from datetime import datetime
import os
import psycopg2
import click
import sys
from psycopg2.extras import RealDictCursor
from hprint import hprint as pprint
# from collections import OrderedDict

logger = logging.getLogger(__name__)

_pg_conn = None

def fatal(msg):
    click.secho(msg, bg='black', fg='red', bold=True, err=True)
    logger.critical(msg)
    sys.exit(1)

def debug(s, logger=logger):
    if logger.isEnabledFor(logging.DEBUG):
        print(f'{datetime.now()}|> {s}')
    logger.debug(s)

def _get_pg_conn(host=None, port=45432, database='cbd', user='cbd', password=None, **kwargs):
    global _pg_conn
    if _pg_conn:
        return _pg_conn
    if not host:
        host = os.getenv("CORGI_PG_HOST")
    try:
        with psycopg2.connect(host=host, port=port, database=database, user=user, password=password) as conn:
            cur = conn.cursor()
            cur.execute('SELECT version()')
            version = cur.fetchone()[0]
            logger.debug(f"[postgres://{user}@{host}:{port})/{database}]: {version}")
            _pg_conn = conn
            return _pg_conn
    except psycopg2.DatabaseError as e:
        fatal(f"failed to connect to postgres: {e}")

# def pg_cursor(host=None, port=45432, database='cbd', user='cbd', password=None, dict_like=True):
def pg_cursor(host=None, dict_like=True, *args, **kwargs):
    cursor = _get_pg_conn(host=host, *args, **kwargs)\
        .cursor(cursor_factory=(RealDictCursor if dict_like else None))
    execute0 = cursor.execute

    def _execute(query, **kwargs):
        if not query.strip().endswith(';'):
            query += ';'
        debug(f"[SQL] {query}")
        return execute0(query, **kwargs)

    cursor.execute = _execute
    return cursor


def pg_execute(statement, *args, **kwargs):
    with pg_cursor(*args, **kwargs) as cur:
        # logger.info(f"Postgres: [{statement}]")
        cur.execute(statement)
        # logger.info("Postgres committing ...")
        cur.connection.commit()
        try:
            return cur.fetchall()
        except Exception:
            pass

def pg_query(statement, *args, **kwargs):
    with pg_cursor(*args, **kwargs) as cur:
        # logger.info(f"Postgres: [{statement}]")
        cur.execute(statement)
        rows = cur.fetchall()
        # logger.info(f"Postgres: {len(rows)} rows fetched")
        result = []
        for row in rows:
            result.append(dict(row))
            # result.append(OrderedDict(row))
        return result

null = click.style("[null]", fg='bright_black')

def execute(ctx, statement='', ddl=False):
    if not statement:
        statement = sys.stdin.read()
    statement = statement.strip()
    # if not statement.lower().startswith('select'):
    if ddl or 'select' not in statement.lower():
        returnings = pg_execute(statement, **ctx.obj)
        if returnings:
            result = []
            for returning in returnings:
                result.append(dict(returning))
                # result.append(OrderedDict(returning))
            pprint(result, as_json=ctx.obj['as_json'], x=ctx.obj['x'], missing_value=null)
    else:
        rows = pg_query(statement, **ctx.obj)
        pprint(rows, as_json=ctx.obj['as_json'], x=ctx.obj['x'], missing_value=null)
