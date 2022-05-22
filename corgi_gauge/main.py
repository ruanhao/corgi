#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import logging
from corgi_common import as_root
from corgi_common.loggingutils import info, config_logging
from corgi_common.scriptutils import run_script_live
import os

config_logging('corgi_gauge', logging.DEBUG)


@click.group(help="CLI tool for all test stuff")
def cli():
    pass

@cli.group()
def io():
    pass

@as_root
@io.command(help='Test block-level reads and writes performance')
@click.option("--partition", '-p', default='/tmp', help='The partition under which to test')
@click.option("--bs", default='1M')
@click.option("--count", default='1024')
@click.option("--dry", is_flag=True)
def block_device_rw_rate(partition, bs, count, dry):
    tempfile_dir = os.path.join(partition, 'iotest')
    tempfile_path = os.path.join(tempfile_dir, 'tempfile')
    script = f'''mkdir -p {tempfile_dir}
echo "=> Write performance testing ..."
dd if=/dev/zero of={tempfile_path} bs={bs} count={count} conv=fdatasync,notrunc
echo "=> Flush caches"
echo 3 | tee /proc/sys/vm/drop_caches
echo "=> Read performance testing ..."
dd if={tempfile_path} of=/dev/null bs={bs} count={count}
'''
    run_script_live(script, dry=dry)


if __name__ == '__main__':
    cli()
