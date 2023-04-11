import click
from .pg_common import execute as e, create_extension
from hprint import hprint
import logging

logger = logging.getLogger(__name__)

@click.group(short_help="[command group] internals")
@click.pass_context
def internals(ctx):
    """postgresql 14 internals"""
    pass

@internals.command(short_help='show isolation/anomalies in PG')
@click.pass_context
def isolations(ctx):
    data = [
        {'level': 'Read Committed', 'lost updates': 'y', 'dirty read': '-', 'non-repeatable reads': 'y', 'phantom reads': 'y', 'other anomalies': 'y'},
        {'level': 'Repeatable Read', 'lost updates': '-', 'dirty read': '-', 'non-repeatable reads': '-', 'phantom reads': '-', 'other anomalies': 'y'},
        {'level': 'Serializable', 'lost updates': '-', 'dirty read': '-', 'non-repeatable reads': '-', 'phantom reads': '-', 'other anomalies': '-'},
    ]
    hprint(data)

@internals.command(short_help='show heap page items')
@click.pass_context
@click.argument("tbl")
@click.option("--page-number", "-n", type=int, default=0, help='nth page of the table')
@click.option("--snapshot", "-s", help="show visibility under snapshot, can get snapshot by `SELECT pg_current_snapshot();`")
@click.option("--raw", is_flag=True)
def heap_page_items(ctx, tbl, page_number, raw, snapshot):
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

    xid = int(e(ctx, "SELECT pg_current_xact_id();", raw=True, as_json=True)[0]['pg_current_xact_id'])
    logger.info(f"xid:{xid}")
    mappings = dict(zip(result[0].keys(), result[0].keys()))
    def _t(b):
        return "t" if b else ""
    for k in ['xmin_committed', 'xmin_aborted', 'xmax_committed', 'xmax_aborted']:
        mappings[k] = (k, _t)

    def _visible(record):
        # if record['xmin_committed'] is False and record['xmin_aborted'] is False:  # xmin transaction not finished yet
        #     v = False
        # elif record['xmin_committed'] is True:
        #     v = True
        # elif record['xmin_aborted'] is True:
        #     v = False
        # xmin = int(record['xmin'])
        # xmax = int(record['xmax'])

        # v1 = xmin <= xid
        # v2 = xid < xmax or xmax == 0
        # v = v and v1 and v2
        # return click.style('t', fg='green') if v else click.style('f', fg='red')
        if not snapshot:
            v = record['visible']
        else:
            xmin, xmax, xip_list = snapshot.split(':')
            xmin = int(xmin)
            xmax = int(xmax)
            xip_list = xip_list.split(',') if xip_list else []  # active xid list
            xip_list = [int(x) for x in xip_list]
            xid = int(record['xmin'])
            if xid < xmin:      # visible unconditionally
                v = True
            elif xid in xip_list:
                v = False
            elif xmin <= xid < xmax:
                v = True
            else:
                v = False
        return click.style('t', fg='green') if v else click.style('f', fg='red')

    mappings['visible'] = ('', _visible)

    def _xmax(xmax):
        if xmax == '0':
            return click.style('undeleted', fg='bright_black')
        return xmax
    mappings['xmax'] = ('xmax', _xmax)
    hprint(result, mappings=mappings, as_json=ctx.obj['as_json'], x=ctx.obj['x'])

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
