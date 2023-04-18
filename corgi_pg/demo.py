import click
from .pg_common import execute as e, create_extension, get_show_result, create_connection, t_describe, relkind, index_info as get_index_info, show_page_layout, show_bt_page_items as show_bt_page
import logging
from corgi_common.scriptutils import pause
import sys
from psycopg2.extensions import ISOLATION_LEVEL_SERIALIZABLE, ISOLATION_LEVEL_REPEATABLE_READ

logger = logging.getLogger(__name__)

@click.group(short_help="[command group] demo")
@click.pass_context
def demo(ctx):
    pass

def _prepare_hot_update(ctx):
    e(ctx, """
DROP TABLE IF EXISTS hot;
CREATE TABLE hot(id integer, s char(2000)) WITH (fillfactor = 75);
CREATE INDEX hot_id ON hot(id);
    """, desc='preparing table and index ...')
    e(ctx, """
DROP FUNCTION IF EXISTS heap_page;
CREATE FUNCTION heap_page(relname text, pageno integer) RETURNS TABLE(
    ctid tid, state text,
    xmin text, xmax text,
    hhu text, hot text, t_ctid tid
) AS $$
    SELECT (pageno,lp)::text::tid AS ctid,
    CASE lp_flags
        WHEN 0 THEN 'unused'
        WHEN 1 THEN 'normal'
        WHEN 2 THEN 'redirect to '||lp_off
        WHEN 3 THEN 'dead'
    END AS state,
    t_xmin || CASE
        WHEN (t_infomask & 256) > 0 THEN ' c'
        WHEN (t_infomask & 512) > 0 THEN ' a'
        ELSE ''
    END AS xmin,
    t_xmax || CASE
        WHEN (t_infomask & 1024) > 0 THEN ' c'
        WHEN (t_infomask & 2048) > 0 THEN ' a'
        ELSE ''
    END AS xmax,
    CASE WHEN (t_infomask2 & 16384) > 0 THEN 't' END AS hhu,
    CASE WHEN (t_infomask2 & 32768) > 0 THEN 't' END AS hot,
    t_ctid
FROM heap_page_items(get_raw_page(relname,pageno)) ORDER BY lp;
$$ LANGUAGE sql;
    """, desc='creating function heap_page ...')
    e(ctx, """
DROP FUNCTION IF EXISTS index_page;
CREATE FUNCTION index_page(relname text, pageno integer) RETURNS TABLE(itemoffset smallint, htid tid, dead boolean) AS $$
    SELECT itemoffset,
    htid,
    dead
FROM bt_page_items(relname,pageno);
$$ LANGUAGE sql;
    """, desc='create proc index_page ...')


def _prepare_table_hot(ctx):
    """\b
    If the s column contains only Latin letters, each heap tuple will have a fixed size of 2004 bytes, plus 24 bytes of the header.

    The fillfactor storage parameter is set to 75%. It means that the page has enough free space for four tuples, but we can insert only three.
    """
    e(ctx, """
DROP TABLE IF EXISTS hot;
CREATE TABLE hot(id integer, s char(2000)) WITH (fillfactor = 75);
CREATE INDEX hot_id ON hot(id);
CREATE INDEX hot_s ON hot(s);
    """, desc='preparing table and index ...')
    e(ctx, """
DROP FUNCTION IF EXISTS heap_page;
CREATE FUNCTION heap_page(relname text, pageno integer) RETURNS TABLE(ctid tid, state text, xmin text, xmax text) AS $$
SELECT (pageno,lp)::text::tid AS ctid,
    CASE lp_flags
        WHEN 0 THEN 'unused'
        WHEN 1 THEN 'normal'
        WHEN 2 THEN 'redirect to '||lp_off
        WHEN 3 THEN 'dead'
    END AS state,
    t_xmin || CASE
        WHEN (t_infomask & 256) > 0 THEN ' c'
        WHEN (t_infomask & 512) > 0 THEN ' a'
        ELSE ''
    END AS xmin,
    t_xmax || CASE
        WHEN (t_infomask & 1024) > 0 THEN ' c'
        WHEN (t_infomask & 2048) > 0 THEN ' a'
        ELSE ''
    END AS xmax
FROM heap_page_items(get_raw_page(relname,pageno)) ORDER BY lp;
$$ LANGUAGE sql;
    """, desc='creating proc heap_page ...')
    e(ctx, """
DROP FUNCTION IF EXISTS index_page;
CREATE FUNCTION index_page(relname text, pageno integer) RETURNS TABLE(itemoffset smallint, htid tid, dead boolean) AS $$
    SELECT itemoffset,
    htid,
    dead
FROM bt_page_items(relname,pageno);
$$ LANGUAGE sql;
    """, desc='create proc index_page ...')

@demo.command(short_help='demo of pruning')
@click.pass_context
def prune(ctx):
    """Postgresql internals section 5.1"""
    _prepare_table_hot(ctx)
    pause("Press Enter to insert/update ...")
    e(ctx, "INSERT INTO hot VALUES (1, 'A');", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'B';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'C';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'D';", share_conn=False)
    e(ctx, "SELECT * FROM heap_page('hot',0);", desc='Now the page contains four tuples:', share_conn=False)
    pause("Press Enter to see that we had exceeded the fillfactor threshold ...")
    show_page_layout(ctx, 'hot')
    pause("Press Enter to trigger page pruning by accessing page ...")
    e(ctx, "UPDATE hot SET s = 'E';", share_conn=False)
    e(ctx, "SELECT * FROM heap_page('hot',0);", desc='a new tuple (0,5) is added into the freed space', share_conn=False)
    pause("Press Enter to see that free space is aggregated ...")
    show_page_layout(ctx, 'hot')
    pause("Press Enter to check all the pointers in the index page are still active so far ...")
    e(ctx, "SELECT * FROM index_page('hot_id',1);")
    pause("Press Enter to trigger index scan and check pointers again ...")
    e(ctx, "select * from hot where id = 1;")
    e(ctx, "SELECT * FROM index_page('hot_id',1);", desc='the 4th item is dead because it is beyond the database horizon')

def _demo_hot_update(ctx, skip_pause=False):
    _prepare_hot_update(ctx)
    pause("Press Enter to insert/update ...", skip_pause)
    e(ctx, """
    INSERT INTO hot VALUES (1, 'A');
    UPDATE hot SET s = 'B';
    """)
    pause("Press Enter to show heap page ...", skip_pause)
    e(ctx, "SELECT * FROM heap_page('hot',0);", share_conn=False)
    # The Heap Hot Updated bit shows that the executor should follow the CTID chain.
    # The Heap Only Tuple bit indicates that this tuple is not referenced from any indexes.
    pause("Press Enter to show index page (notice that (0,2) is not there)...", skip_pause)
    show_bt_page(ctx, "hot_id")
    pause("Press Enter to further update and check heap page ...", skip_pause)
    e(ctx, "UPDATE hot SET s = 'C';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'D';", share_conn=False)
    e(ctx, "SELECT * FROM heap_page('hot',0);", share_conn=False)
    e(ctx, "SELECT * FROM index_page('hot_id',1);", desc='index still contains only one reference, which points to the head of this chain')

@demo.command(short_help='demo of Heap Only Tuple update')
@click.pass_context
def hot_update(ctx):
    _demo_hot_update(ctx)
    pass

def _demo_for_hot_update(ctx, skip_pause=False):
    pause("Press enter to trigger page pruning ...", skip_pause)
    e(ctx, "UPDATE hot SET s = 'E';", share_conn=False)
    e(ctx, "SELECT * FROM heap_page('hot',0);", desc="(0,1), (0,2), and (0,3) have been pruned (new tuple is written into the freed space as tuple (0,2))")

@demo.command(short_help='demo of prune with hot updates')
@click.pass_context
def prune_for_hot_update(ctx):
    _demo_hot_update(ctx, True)
    # the fillfactor threshold is already exceeded at this line
    _demo_for_hot_update(ctx)

@demo.command(short_help='demo of hot chain split')
@click.pass_context
def hot_chain_split(ctx):
    _demo_hot_update(ctx, True)
    # the fillfactor threshold is already exceeded at this line
    _demo_for_hot_update(ctx, True)
    e(ctx, "UPDATE hot SET s = 'F';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'G';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'H';", share_conn=False)
    pause("enter to create a transaction to block pruning ...")
    conn = create_connection(ctx, isolation_level=ISOLATION_LEVEL_REPEATABLE_READ)
    e(ctx, "select 1;", connection=conn, commit=False)

    e(ctx, "UPDATE hot SET s = 'I';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'J';", share_conn=False)
    e(ctx, "UPDATE hot SET s = 'K';", share_conn=False)

    e(ctx, "SELECT * FROM heap_page('hot',0);", desc='init state')
    pause("enter to update, thus create a new heap page ...")
    e(ctx, "UPDATE hot SET s = 'L'")
    pause("enter to check heap page 0 ...")
    e(ctx, "SELECT * FROM heap_page('hot',0);")
    pause("enter to check heap page 1 ...")
    e(ctx, "SELECT * FROM heap_page('hot',1);")
    pause("enter to check index page 1 ...")
    e(ctx, "SELECT * FROM index_page('hot_id',1);")


def _show_si_readlocks(ctx):
    e(ctx, "SELECT relation::regclass, locktype, page, tuple FROM pg_locks WHERE mode = 'SIReadLock';")

@demo.command(short_help='demo of how write-skew is handled in Serializable Snapshot Isolation')
@click.pass_context
def write_skew(ctx):
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

@demo.command(short_help='demo of index correlation')
@click.pass_context
def index_correlation(ctx):
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

@demo.command(short_help='demo of false-positive write-skew using sequential scan')
@click.pass_context
def write_skew_false_positive_seq_scan(ctx):
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