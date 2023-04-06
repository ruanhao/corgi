import click
from .pg_common import execute as e


@click.group(short_help="[command group] internals")
@click.pass_context
def internals(ctx):
    """postgresql 14 internals"""
    pass

@internals.command(short_help='show page layout')
@click.pass_context
@click.argument("tbl")
@click.option("--page-number", "-n", type=int, default=0, help='nth page of the table')
def page_layout(ctx, tbl, page_number):
    e(ctx, "CREATE EXTENSION IF NOT EXISTS pageinspect;")
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
