import click
import logging
from corgi_common import pretty_print, bye, run_script

client = None

logger = logging.getLogger(__name__)

def fatal(msg):
    logger.critical(msg)
    bye(msg)

def info(msg):
    logger.info(msg)
    click.echo(msg)

def _run(script):
    rc, stdout, stderr = run_script(script, capture=True)
    if rc:
        bye(stderr)
    pretty_print(stdout.strip())

@click.group(help="Utils for IAM")
def iam():
    _run('aws iam get-user --query "User.Arn" --output text')
    pass


@iam.command(help="Account ID")
def account_id():

    pass
