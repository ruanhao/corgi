#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from .vm import vm
from .host import host
from .folder import folder
from .dc import datacenter
from .ds import datastore
from .rp import resource_pool
from corgi_common import config_logging
import logging

config_logging('corgi_vcenter', logging.DEBUG)


@click.group(help="CLI tool for VCENTER management")
@click.pass_context
@click.option('--url', '-h', envvar='GOVC_URL', required=True, help='ENV[GOVC_URL]')
@click.option('--username', '-u', envvar='GOVC_USERNAME', required=True, help='ENV[GOVC_USERNAME]')
@click.option('--password', '-p', envvar='GOVC_PASSWORD', required=True, help='ENV[GOVC_PASSWORD]')
def cli(ctx, url, username, password):
    ctx.ensure_object(dict)
    ctx.obj = {
        'url': url,
        'username': username,
        'password': password,
    }
    pass


cli.add_command(vm)
cli.add_command(host)
cli.add_command(folder)
cli.add_command(datacenter)
cli.add_command(datastore)
cli.add_command(resource_pool)


if __name__ == '__main__':
    cli()
