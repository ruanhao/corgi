#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common.loggingutils import config_logging
from .tutorial import tutorial
import logging

logger = logging.getLogger(__name__)

@click.group(help="CLI tool for Postgres")
def cli():
    pass


cli.add_command(tutorial)

def main():
    config_logging('corgi_pg')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
