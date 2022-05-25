#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging
from .ova import ova

@click.group(help="Build utils")
def cli():
    pass


def main():
    config_logging('corgi_build')

    cli.add_command(ova)

    cli()


if __name__ == '__main__':
    main()
