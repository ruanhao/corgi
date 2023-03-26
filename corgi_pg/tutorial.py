import click
import logging
from .pg_common import execute
from corgi_common.scriptutils import run_script_live
from corgi_common.pathutils import get_local_file_path

logger = logging.getLogger(__name__)


@click.group(help="tutorial scripts for https://www.postgresqltutorial.com/")
@click.pass_context
@click.option('--hostname', envvar='CORGI_PG_HOST', show_default=True, required=True)
@click.option('--port', envvar='CORGI_PG_PORT', default=5672, type=int)
@click.option('--user', envvar='CORGI_PG_USER', required=True)
@click.option('--database', envvar='CORGI_PG_DATABASE', default='dvdrental')
@click.option('--password', '-p', envvar='CORGI_PG_PASSWORD')
@click.option('--json', '-json', 'as_json', is_flag=True)
@click.option('-x', is_flag=True)
def tutorial(ctx, hostname, port, user, password, database, as_json, x):
    ctx.ensure_object(dict)
    ctx.obj['user'] = user
    ctx.obj['password'] = password
    ctx.obj['database'] = database
    ctx.obj['host'] = hostname
    ctx.obj['port'] = port
    ctx.obj['as_json'] = as_json
    ctx.obj['x'] = x
    pass

@tutorial.command()
@click.pass_context
def test(ctx):
    execute(ctx, "select version();")
#    print("test")

@tutorial.command(help="drop/reload database")
@click.pass_context
def reload(ctx):
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
        cur_ob.execute(f"DROP DATABASE {db};")
        cur_ob.execute("CREATE USER postgres SUPERUSER;")
    except Exception:
        pass
    cur_ob.execute(f"CREATE DATABASE {db};")

    dir_path = get_local_file_path("dvdrental")
    command = f"""pg_restore -h {ctx.obj['host']} -p {ctx.obj['port']} -U {ctx.obj['user']} -d {db}"""
    if ctx.obj['password']:
        command += """ -W {ctx.obj['password']}"""
    command += f" {dir_path}"
    print("reloading ...")
    run_script_live(command)
    print("done.")
