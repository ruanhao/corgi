#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging
import logging
from .ova import ova

config_logging('corgi_build', logging.DEBUG)

@click.group(help="Build utils")
def cli():
    pass


if __name__ == '__main__':
    cli()


cli.add_command(ova)
