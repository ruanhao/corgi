import click
from .pg_common import execute as e, psql, explain

@click.group(help="[command group]")
@click.pass_context
def index(ctx):
    pass

@index.command()
@click.pass_context
def by_index_scan(ctx):
    e(ctx, """
DROP TABLE IF EXISTS t;
create table t(a integer, b text, c boolean);
    """)
    e(ctx, """
INSERT INTO t(a,b,c)
  SELECT s.id, chr((32+random()*94)::integer), random() < 0.01
  FROM generate_series(1,100000) as s(id)
  ORDER BY random();
    """)
    e(ctx, """
CREATE INDEX on t(a);
analyze t;
    """)
    explain(ctx, "select * from t where a = 1;", costs=False)
    # explain(ctx, "select * from t where a = 1;", costs=True)
    pass

@index.command()
@click.pass_context
def by_bitmap_scan(ctx):
    e(ctx, """
DROP TABLE IF EXISTS t;
create table t(a integer, b text, c boolean);
    """)
    e(ctx, """
INSERT INTO t(a,b,c)
  SELECT s.id, chr((32+random()*94)::integer), random() < 0.01
  FROM generate_series(1,100000) as s(id)
  ORDER BY random();
    """)
    e(ctx, """
CREATE INDEX on t(a);
analyze t;
    """)
    explain(ctx, "select * from t where a <= 100;")
    # explain(ctx, "select * from t where a = 1;", costs=True)
    pass