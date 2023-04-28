import logging
import re
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
        sc = _pg_conns[isolation_level]
        iso = sc.isolation_level or ISOLATION_LEVEL_AUTOCOMMIT
        iso_name = _iso_names[iso]
        logger.debug(f"[connection reused] {sc} [isolation:{iso_name}({iso})]")
        _set_connection_readonly(sc, readonly)
        _set_connection_deferrable(sc, deferrable)
        return sc

    try:
        with psycopg2.connect(host=host, port=port, database=database, user=user, password=password) as conn:
            # logger.debug(f"[connection created] [postgres://{user}@{host}:{port})/{database}] server version: {conn.server_version}, protocol version: {conn.protocol_version}")
            logger.info(f"[connection created] [{conn.dsn}] server version: {conn.server_version}, protocol version: {conn.protocol_version}")
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
        click.secho('-> ' + desc, underline=True)
    if ctx.obj.get('dry'):
        print(statement)
        return
    isolation_level0 = ctx.obj['isolation_level']
    try:
        if isolation_level is not None:
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
    if ctx.obj['dry']:
        return None
    as_json0 = ctx.obj['as_json']
    try:
        ctx.obj['as_json'] = True
        result = execute(ctx, f"SHOW {key};", raw=True)
        value = result[0][key]
        return (extractor or (lambda value: value))(value)
    finally:
        ctx.obj['as_json'] = as_json0

def reload_conf(ctx):
    execute(ctx, "SELECT pg_reload_conf();", raw=True)

def create_extension(ctx, extension):
    execute(ctx, f"CREATE EXTENSION IF NOT EXISTS {extension};")

def t_describe(ctx, tbl):
    psql(ctx, "\d " + tbl)

def relkind(ctx, relname):
    return execute(ctx, f"select relkind from pg_class where relname='{relname}'", raw=True, as_json=True)[0]['relkind']


def index_info(ctx, tbl=None):
    """https://stackoverflow.com/a/2213199/1267982"""
    t_sql = f"and t.relname = '{tbl}'" if tbl else ''
    sql = f"""
select
    t.relname as table_name,
    i.relname as index_name,
    array_to_string(array_agg(a.attname), ', ') as column_names
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
    -- and t.relname like 'test%'
    {t_sql}
group by
    t.relname,
    i.relname
order by
    t.relname,
    i.relname;
    """
    return execute(ctx, sql, raw=True, as_json=True)

def _visible0(record, xid: int, snapshot_xmin: int, snapshot_xmax: int, snapshot_xip_list: list[int]):
    """This is not the full set of visibility rules. For example, without taking cid into consideration.
    """
    t_xmin = int(record['xmin'])
    t_xmax = int(record['xmax'])
    t_xmin_committed = record['xmin_committed']
    t_xmin_aborted = record['xmin_aborted']
    t_xmax_committed = record['xmax_committed']
    t_xmax_aborted = record['xmax_aborted']

    t_xmin_active = (t_xmin >= snapshot_xmax) or (t_xmin in snapshot_xip_list)
    t_xmax_active = (t_xmax >= snapshot_xmax) or (t_xmax in snapshot_xip_list)

    if t_xmin_aborted:          # t_xmin status == ABORTED
        return False
    if not t_xmin_committed and not t_xmin_aborted:  # t_xmin status == IN_PROGRESS
        if xid == t_xmin:
            # t_xmax != 0 means this tuple has been deleted or updated by the current transaction itself
            return t_xmax == 0
        else:
            return False
    if t_xmin_committed:
        if t_xmin_active:
            return False
        elif t_xmax == 0 or t_xmax_aborted:
            return True
        elif not t_xmax_committed and not t_xmax_aborted:  # t_xmax status is 'IN_PROGRESS'
            return t_xmax != xid
        elif t_xmax_committed:
            return t_xmax_active

def show_heap_page(ctx, tbl, page_number=0, xid=None):
    """show heap page for heap table"""
    execute(ctx, f"SELECT * FROM {tbl};", raw=True)  # just in order to update information bits
    create_extension(ctx, 'pageinspect')

    result = execute(ctx, f"""
SELECT
    '({page_number},'||t1.lp||')' AS tid,
    t1.t_ctid,
    t_field3 as t_cid, -- how many SQL commands were executed before this command was executed within the current transaction beginning from 0
    CASE t1.lp_flags
        WHEN 0 THEN 'unused'
        WHEN 1 THEN 'normal'
        -- WHEN 2 THEN 'redirect to '||lp_off
        WHEN 2 THEN 'redirect to '||'({page_number},'||t1.lp_off||')'
        WHEN 3 THEN 'dead'
    END AS state,
    t1.t_xmin as xmin,
    (t1.t_infomask & 256) > 0 AS xmin_committed,
    (t1.t_infomask & 512) > 0 AS xmin_aborted,
    t1.t_xmax as xmax,
    (t1.t_infomask & 1024) > 0 AS xmax_committed,
    (t1.t_infomask & 2048) > 0 AS xmax_aborted,
    -- t2.ctid,
    (t1.t_infomask2 & 16384) > 0 AS hot_updated,
    (t1.t_infomask2 & 32768) > 0 AS heap_only,
    t2.ctid IS NOT NULL AS visible
    -- encode(t_data, 'escape') AS decoded
FROM heap_page_items(get_raw_page('{tbl}', {page_number})) AS t1
LEFT JOIN {tbl} AS t2 ON ('({page_number},'||t1.lp||')')::tid = t2.ctid
    """, raw=True, as_json=True)

    # xid = int(e(ctx, "SELECT pg_current_xact_id();", raw=True, as_json=True)[0]['pg_current_xact_id'])
    # logger.info(f"xid:{xid}")
    mappings = dict(zip(result[0].keys(), result[0].keys()))
    def _t(b):
        return "t" if b else ""
    for k in ['xmin_committed', 'xmin_aborted', 'xmax_committed', 'xmax_aborted', 'hot_updated', 'heap_only']:
        mappings[k] = (k, _t)

    if xid:
        assert snapshot, 'must specify snapshot when xid is supplied'
        snapshot_xmin, snapshot_xmax, snapshot_xip_list = snapshot.split(':')
        snapshot_xmin = int(snapshot_xmin)
        snapshot_xmax = int(snapshot_xmax)
        snapshot_xip_list = snapshot_xip_list.split(',') if snapshot_xip_list else []  # active xid list
        snapshot_xip_list = [int(x) for x in snapshot_xip_list]
    def _visible(record):
        if not xid or not snapshot:
            v = record['visible']
        else:
            v = _visible0(record, xid, snapshot_xmin, snapshot_xmax, snapshot_xip_list)
        return click.style('t', fg='green') if v else click.style('f', fg='red')

    mappings['visible'] = ('', _visible)

    def _xmax(xmax):
        if xmax == '0':
            return click.style('undeleted', fg='bright_black')
        return xmax
    mappings['xmax'] = ('xmax', _xmax)
    pprint(result, mappings=mappings, as_json=ctx.obj['as_json'], x=ctx.obj['x'])

def show_bt_page_items(ctx, tbl, page_number=1):
    """page number starts from 1, the zero page is used for meta-data"""
    index_info = execute(ctx, f"""
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public' and indexname = '{tbl}'
ORDER BY tablename, indexname;
        """, raw=True, as_json=True)[0]
    tablename = index_info['tablename']
    indexdef = index_info['indexdef']
    m = re.match(r"^.*\((.*)\)$", indexdef)
    columns = m.group(1).split(',')
    columns_sql = ','.join([f"t.{c} AS t_{c}" for c in columns])
    sql = f"""
SELECT
        p.itemoffset,
        CASE p.dead
            WHEN true THEN 't'
            ELSE 'f'
        END AS dead,
        -- p.dead,
        p.htid, -- ctid before v.13
        p.data,
        -- ('x' || lpad(REPLACE(p.data, ' ', ''), 16, '0'))::bit(64)::bigint AS data_int,
        {columns_sql}
FROM bt_page_items('{tbl}', {page_number}) as p
LEFT JOIN {tablename} AS t ON p.htid = t.ctid
        ;
        """
    execute(ctx, sql)

def show_page_layout(ctx, tbl, page_number=0):
    create_extension(ctx, 'pageinspect')
    data = execute(ctx, f"""
SELECT lower, upper, special, pagesize
FROM page_header(get_raw_page('{tbl}', {page_number}));
    """, raw=True, as_json=True)[0]
    # [{'lower': 64, 'upper': 7432, 'special': 8192, 'pagesize': 8192}]
    lower = data['lower']
    upper = data['upper']
    special = data['special']
    pagesize = data['pagesize']
    if special != pagesize:
        print(f"""+---------------------------------------+ 0
|               header                  |
+---------------------------------------+ 24
|       array of item pointers          |
+---------------------------------------+ {lower}
|             free space                |
+---------------------------------------+ {upper}
|        items (row versions)           |
+---------------------------------------+ {special}
|           special space               |
+---------------------------------------+ {pagesize}""")
    else:
        print(f"""+---------------------------------------+ 0
|               header                  |
+---------------------------------------+ 24
|       array of item pointers          |
+---------------------------------------+ {lower}
|             free space                |
+---------------------------------------+ {upper}
|        items (row versions)           |
+---------------------------------------+ {special}""")


def create_function_buffercache(ctx):
    create_extension(ctx, "pg_buffercache")
    execute(ctx, """
DROP FUNCTION IF EXISTS buffercache(regclass);
-- DROP FUNCTION IF EXISTS buffercache;
CREATE FUNCTION buffercache(rel regclass) RETURNS TABLE(
    bufferid integer, relfork text, relblk bigint,
    isdirty boolean, usagecount smallint, pins integer
) AS $$
    SELECT bufferid,
    CASE relforknumber
        WHEN 0 THEN 'main'
        WHEN 1 THEN 'fsm'
        WHEN 2 THEN 'vm'
    END,
    relblocknumber, isdirty, usagecount, pinning_backends
    FROM pg_buffercache
    WHERE relfilenode = pg_relation_filenode(rel)
    ORDER BY relforknumber, relblocknumber;
    $$ LANGUAGE sql;
    """)

def show_heap_io(ctx, relation):
    """heap_blks_hit: cache hit
heap_blks_read: cache miss
    """
    execute(ctx, f"""
SELECT heap_blks_read, heap_blks_hit
    FROM pg_statio_all_tables
WHERE relname = '{relation}';
    """)
