import click
from .pg_common import execute as e, create_extension, get_show_result, create_connection, t_describe
from corgi_common.scriptutils import pause
from hprint import hprint
import logging
import sys
from psycopg2.extensions import ISOLATION_LEVEL_SERIALIZABLE

logger = logging.getLogger(__name__)

@click.group(short_help="[command group] internals")
@click.pass_context
def internals(ctx):
    """postgresql 14 internals"""
    pass


@internals.command(short_help='demo of index correlation')
@click.pass_context
def demo_index_correlation(ctx):
    e(ctx, """
DROP TABLE IF EXISTS tbl_corr;
CREATE TABLE tbl_corr (col text, col_asc int, col_desc int, col_rand int);
INSERT INTO tbl_corr VALUES
    ('Tuple_1', 1, 12, 3),
    ('Tuple_2', 2, 11, 8),
    ('Tuple_3', 3, 10, 5),
    ('Tuple_4', 4, 9, 9),
    ('Tuple_5', 5, 8, 7),
    ('Tuple_6', 6, 7, 2),
    ('Tuple_7', 7, 6, 10),
    ('Tuple_8', 8, 5, 11),
    ('Tuple_9', 9, 4, 4),
    ('Tuple_10', 10, 3, 1),
    ('Tuple_11', 11, 2, 12),
    ('Tuple_12', 12, 1, 6);

CREATE INDEX tbl_corr_asc_idx ON tbl_corr (col_asc);
CREATE INDEX tbl_corr_desc_idx ON tbl_corr (col_desc);
CREATE INDEX tbl_corr_rand_idx ON tbl_corr (col_rand);

ANALYZE tbl_corr;
    """)
    # t_describe(ctx, 'tbl_corr')
    e(ctx, "SELECT attname, correlation FROM pg_stats WHERE tablename = 'tbl_corr';")

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

@internals.command(short_help='demo of how write-skew is handled in Serializable Snapshot Isolation')
@click.pass_context
def demo_write_skew(ctx):
    """\b
    write-skew can be observed in isolation other than SERIALIZABLE.

    See http://www.interdb.jp/pg/pgsql05.html 5.9.3
    """
    pause("Press Enter to initialize test table...")
    e(
        ctx,
        """
DROP TABLE IF EXISTS tbl;
CREATE TABLE tbl (id INT primary key, flag bool DEFAULT false);
INSERT INTO tbl (id) SELECT generate_series(1,2000);
ANALYZE tbl;
"""
    )
    if '-i' in sys.argv or '--isolation-level' in sys.argv:
        il = ctx.obj.get('isolation_level')
    else:
        il = ISOLATION_LEVEL_SERIALIZABLE
    conn_tx_a = create_connection(ctx, isolation_level=il)
    conn_tx_b = create_connection(ctx, isolation_level=il)
    pause("[Tx A] Press Enter to read ...")
    e(ctx, "select * from tbl where id = 2000;", connection=conn_tx_a, commit=False)
    _show_si_readlocks(ctx)
    pause("[Tx B] Press Enter to read ...")
    e(ctx, "select * from tbl where id = 1;", connection=conn_tx_b, commit=False)
    _show_si_readlocks(ctx)

    pause("[Tx A] Press Enter to update ...")
    e(ctx, "UPDATE tbl set flag = TRUE where id = 1;", connection=conn_tx_a, commit=False)
    _show_si_readlocks(ctx)
    pause("[Tx B] Press Enter to update ...")
    e(ctx, "UPDATE tbl set flag = TRUE where id = 2000;", connection=conn_tx_b, commit=False)
    _show_si_readlocks(ctx)

    pause("[Tx A] Press Enter to commit ...")
    conn_tx_a.commit()
    pause("[Tx B] Press Enter to commit ...")
    try:
        conn_tx_b.commit()
    except Exception as ex:
        print(ex)

@internals.command(short_help='demo of false-positive write-skew using sequential scan')
@click.pass_context
def demo_write_skew_false_positive_seq_scan(ctx):
    """\b
    to observe relation level SIREAD lock (using sequential scan)
    """
    pause("Press Enter to initialize test table...")
    e(
        ctx,
        """
DROP TABLE IF EXISTS tbl;
CREATE TABLE tbl (id INT, flag bool DEFAULT false);
INSERT INTO tbl (id) SELECT generate_series(1,20);
ANALYZE tbl;
"""
    )
    if '-i' in sys.argv or '--isolation-level' in sys.argv:
        il = ctx.obj.get('isolation_level')
    else:
        il = ISOLATION_LEVEL_SERIALIZABLE
    conn_tx_a = create_connection(ctx, isolation_level=il)
    conn_tx_b = create_connection(ctx, isolation_level=il)
    pause("[Tx A] Press Enter to read ...")
    e(ctx, "select * from tbl where id = 1;", connection=conn_tx_a, commit=False)
    _show_si_readlocks(ctx)
    pause("[Tx B] Press Enter to read ...")
    e(ctx, "select * from tbl where id = 2;", connection=conn_tx_b, commit=False)
    _show_si_readlocks(ctx)

    pause("[Tx A] Press Enter to update ...")
    e(ctx, "UPDATE tbl set flag = TRUE where id = 1;", connection=conn_tx_a, commit=False)
    _show_si_readlocks(ctx)
    pause("[Tx B] Press Enter to update ...")
    e(ctx, "UPDATE tbl set flag = TRUE where id = 2;", connection=conn_tx_b, commit=False)
    _show_si_readlocks(ctx)

    pause("[Tx A] Press Enter to commit ...")
    conn_tx_a.commit()
    pause("[Tx B] Press Enter to commit ...")
    try:
        conn_tx_b.commit()
    except Exception as ex:
        print(ex)

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
SELECT *, round(100 * avail/{bs},2) as "freespace ratio" FROM pg_freespace('{tbl}');
    """)

@internals.command(short_help='show heap page items')
@click.pass_context
@click.argument("tbl")
@click.option("--page-number", "-n", type=int, default=0, help='nth page of the table')
@click.option("--snapshot", "-s", help="show visibility under snapshot, can get snapshot by `SELECT pg_current_snapshot();`")
@click.option("--xid", "-x", type=int, help="current txid, can get by `SELECT pg_current_xact_id();`", default=None)
@click.option("--raw", is_flag=True)
def heap_page_items(ctx, tbl, page_number, raw, snapshot, xid):
    """\b
- xmax
  if it is 0(dummy number), means this tuple has not been deleted and represents the current version of the row.
  Transactions will ignore this number when the xmax_aborted bit is set.
    """
    create_extension(ctx, 'pageinspect')
    e(ctx, f"SELECT * FROM {tbl};", raw=True)  # just in order to update information bits
    if raw:
        e(ctx, f"""SELECT * FROM heap_page_items(get_raw_page('{tbl}', {page_number}))""")
        return
    result = e(ctx, f"""
SELECT
    '({page_number},'||t1.lp||')' AS tid,
    t1.t_ctid,
    t_field3 as t_cid, -- how many SQL commands were executed before this command was executed within the current transaction beginning from 0
    CASE t1.lp_flags
        WHEN 0 THEN 'unused'
        WHEN 1 THEN 'normal'
        WHEN 2 THEN 'redirect to '||lp_off
        WHEN 3 THEN 'dead'
    END AS state,
    t1.t_xmin as xmin,
    (t1.t_infomask & 256) > 0 AS xmin_committed,
    (t1.t_infomask & 512) > 0 AS xmin_aborted,
    t1.t_xmax as xmax,
    (t1.t_infomask & 1024) > 0 AS xmax_committed,
    (t1.t_infomask & 2048) > 0 AS xmax_aborted,
    -- t2.ctid,
    t2.ctid IS NOT NULL AS visible
FROM heap_page_items(get_raw_page('{tbl}', {page_number})) AS t1
LEFT JOIN {tbl} AS t2 ON ('({page_number},'||t1.lp||')')::tid = t2.ctid
    """, raw=True, as_json=True)

    # xid = int(e(ctx, "SELECT pg_current_xact_id();", raw=True, as_json=True)[0]['pg_current_xact_id'])
    # logger.info(f"xid:{xid}")
    mappings = dict(zip(result[0].keys(), result[0].keys()))
    def _t(b):
        return "t" if b else ""
    for k in ['xmin_committed', 'xmin_aborted', 'xmax_committed', 'xmax_aborted']:
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
    hprint(result, mappings=mappings, as_json=ctx.obj['as_json'], x=ctx.obj['x'])

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


@internals.command(short_help='show page layout')
@click.pass_context
@click.argument("tbl")
@click.option("--page-number", "-n", type=int, default=0, help='nth page of the table')
def page_layout(ctx, tbl, page_number):
    # e(ctx, "CREATE EXTENSION IF NOT EXISTS pageinspect;")
    create_extension(ctx, 'pageinspect')
    data = e(ctx, f"""
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
