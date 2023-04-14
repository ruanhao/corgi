import click
import logging
from .pg_common import execute
from corgi_common.scriptutils import run_script_live
from corgi_common.pathutils import get_local_file_path
from .select import select
from .dml import dml
from .ddl import ddl
from .types import types
from .condition import condition
from .constraint import constraint

logger = logging.getLogger(__name__)


@click.group(help="[command group] tutorial scripts for https://www.postgresqltutorial.com/")
@click.pass_context
def tutorial(ctx):
    pass


@tutorial.command(short_help="drop/reload database")
@click.pass_context
def reload(ctx):
    """https://www.postgresqltutorial.com/postgresql-getting-started/load-postgresql-sample-database/"""
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    postgresConnection = psycopg2.connect(
        host=ctx.obj['host'],
        port=ctx.obj['port'],
        user=ctx.obj['user'],
        password=ctx.obj['password'],
    )
    postgresConnection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT);

    db = ctx.obj['database']
    cur_ob = postgresConnection.cursor()
    try:
        cur_ob.execute(f"DROP DATABASE IF EXISTS {db};")
        cur_ob.execute("CREATE USER postgres SUPERUSER;")
    except Exception:
        pass
    cur_ob.execute(f"CREATE DATABASE {db} WITH OWNER {ctx.obj['user']};")

    dir_path = get_local_file_path("dvdrental")
    command = f"""pg_restore -v -h {ctx.obj['host']} -p {ctx.obj['port']} -U {ctx.obj['user']} -d {db}"""
    if ctx.obj['password']:
        command += """ -W {ctx.obj['password']}"""
    command += f" {dir_path}"
    print("reloading ...")
    run_script_live(command)
    execute(ctx, """SELECT schemaname, tablename, tableowner FROM pg_catalog.pg_tables WHERE schemaname = 'public';""")
    print()
    print("done.")

tutorial.add_command(select, "query")
tutorial.add_command(dml)
tutorial.add_command(ddl)
tutorial.add_command(condition)
tutorial.add_command(constraint)
tutorial.add_command(types)