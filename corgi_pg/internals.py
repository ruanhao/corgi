import click
from .pg_common import (
    execute as e,
    create_extension,
    get_show_result,
    create_connection,
    t_describe,
    relkind,
    index_info as get_index_info,
    show_heap_page,
    show_bt_page_items,
    show_page_layout,
)
from corgi_common.scriptutils import pause
from hprint import hprint
import logging
import sys
from psycopg2.extensions import ISOLATION_LEVEL_SERIALIZABLE
import re

logger = logging.getLogger(__name__)

@click.group(short_help="[command group] internals")
@click.pass_context
def internals(ctx):
    """postgresql 14 internals"""
    pass

def _show_si_readlocks(ctx):
    e(ctx, "SELECT relation::regclass, locktype, page, tuple FROM pg_locks WHERE mode = 'SIReadLock';")

@internals.command(short_help='show locks')
@click.pass_context
@click.option("--mode", '-m', type=click.Choice(['SIReadLock', 'AccessShareLock', 'ExclusiveLock']))
def locks(ctx, mode):
    if not mode:
        e(ctx, "SELECT relation::regclass, mode, locktype, page, tuple FROM pg_locks;")
    else:
        e(ctx, f"SELECT relation::regclass, mode, locktype, page, tuple FROM pg_locks where mode = '{mode}';")

@internals.command(short_help='show isolation/anomalies in PG')
@click.pass_context
def isolations(ctx):
    data = [
        {'level': 'Read Committed', 'lost updates': 'y', 'dirty read': '-', 'non-repeatable reads': 'y', 'phantom reads': 'y', 'other anomalies': 'y'},
        {'level': 'Repeatable Read', 'lost updates': '-', 'dirty read': '-', 'non-repeatable reads': '-', 'phantom reads': '-', 'other anomalies': 'y'},
        {'level': 'Serializable', 'lost updates': '-', 'dirty read': '-', 'non-repeatable reads': '-', 'phantom reads': '-', 'other anomalies': '-'},
    ]
    hprint(data)

@internals.command(short_help='show free space for table/index')
@click.pass_context
@click.argument("tbl")
def freespace(ctx, tbl):
    create_extension(ctx, 'pg_freespacemap')
    bs = get_show_result(ctx, 'block_size')
    e(ctx, f"""
SELECT *, round(100 * avail/{bs},2) as "freespace ratio (%)" FROM pg_freespace('{tbl}');
    """)

    e(ctx, f"""
SELECT count(*) as "pages",
       pg_size_pretty(cast(avg(avail) as bigint)) as "Avg freespace size",
       round(100 * avg(avail)/{bs}, 2) AS "Avg freespace ratio (%)"
       FROM pg_freespace('{tbl}');
    """, desc="overall average")

@internals.command(short_help='show heap page items')
@click.pass_context
@click.argument("tbl")
@click.option("--page-number", "-n", type=int, default=0, help='nth page of the table')
@click.option("--snapshot", "-s", help="show visibility under snapshot, can get snapshot by `SELECT pg_current_snapshot();`")
@click.option("--xid", "-x", type=int, help="current txid, can get by `SELECT pg_current_xact_id();`", default=None)
@click.option("--raw", is_flag=True)
def heap_page(ctx, tbl, page_number, raw, snapshot, xid):
    """\b
- xmax
  if it is 0(dummy number), means this tuple has not been deleted and represents the current version of the row.
  Transactions will ignore this number when the xmax_aborted bit is set.
    """
    create_extension(ctx, 'pageinspect')
    if raw:
        if relkind(ctx, tbl) == 'i':
            e(ctx, f"select * from bt_page_items('{tbl}', {page_number + 1});")
            return
        e(ctx, f"""SELECT * FROM heap_page_items(get_raw_page('{tbl}', {page_number}))""")
        return

    if relkind(ctx, tbl) == 'i':
        show_bt_page_items(ctx, tbl, page_number + 1)
        return
    show_heap_page(ctx, tbl, page_number, xid)

@internals.command(short_help='show page layout')
@click.pass_context
@click.argument("tbl")
@click.option("--page-number", "-n", type=int, default=0, help='nth page of the table')
def page_layout(ctx, tbl, page_number):
    show_page_layout(ctx, tbl, page_number)
