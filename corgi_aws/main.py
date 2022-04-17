#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging
from .ec2 import ec2
from .cf import cf
from .route53 import route53
import logging
from .common import check_aws_credential

config_logging('corgi_aws', logging.DEBUG)

@click.group(help="CLI tool for AWS management")
def cli():
    check_aws_credential()
    pass


cli.add_command(ec2)
cli.add_command(cf)
cli.add_command(route53)


if __name__ == '__main__':
    cli()
