#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging, pretty_print, bye
from .ec2 import ec2
from .iam import iam
from .cf import cf
from .s3 import s3
from .sqs import sqs
from .route53 import route53
from .lambda_ import lambda_
from corgi_common.pathutils import get_local_file_path
from .common import check_aws_credential
from requests import get
import json

# Or can just click in the GUI: https://awspolicygen.s3.amazonaws.com/policygen.html
AWS_POLICIES_FILE_URL = 'https://awspolicygen.s3.amazonaws.com/js/policies.js'

def __get_policies():
    try:
        r = get(AWS_POLICIES_FILE_URL)
        if not r.ok:
            raise Exception("Try local file instead")
        t = r.text
    except Exception:
        with open(get_local_file_path('policies.js'), 'r') as f:
            t = f.read()
    t = t.split('=')[1]
    return json.loads(t)


@click.group(help="CLI tool for AWS management", context_settings=dict(help_option_names=['-h', '--help']))
def cli():
    check_aws_credential()
    pass

@cli.group(help="AWS Policy")
def policy():
    pass

@policy.command(help="List all services")
def list_services():
    policies = __get_policies()
    service_map = policies['serviceMap']
    result = []
    for k, v in service_map.items():
        result.append({'service-name': k, 'prefix': v['StringPrefix']})
    pretty_print(result, mappings={'Service': 'service-name', 'Prefix': 'prefix'})

@policy.command(help="List all actions of a service")
@click.argument("service-name")
def list_actions(service_name):
    policies = __get_policies()
    service_map = policies['serviceMap']
    service_map_by_prefix = {v['StringPrefix']: v for k, v in service_map.items()}
    if service_name not in service_map and service_name not in service_map_by_prefix:
        bye(f"Invalid service ({service_name})")
    service = service_map.get(service_name)
    if not service:
        service = service_map_by_prefix[service_name]
    prefix = service['StringPrefix']
    for action in service['Actions']:
        click.echo(f"{prefix}:{action}")


cli.add_command(ec2)
cli.add_command(cf)
cli.add_command(route53)
cli.add_command(iam)
cli.add_command(s3)
cli.add_command(sqs)
cli.add_command(lambda_, "lambda")

def main():
    config_logging('corgi_aws')
    cli()


if __name__ == '__main__':
    main()
