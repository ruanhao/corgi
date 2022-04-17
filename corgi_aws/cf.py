import click
import logging
import boto3
from tabulate import tabulate

ec2_client = boto3.client('ec2')

logger = logging.getLogger(__name__)


def truncate(s, limit=30):
    return (s[:limit] + '..') if len(s) > limit  else s


def get_instance_id_from_output(stack):
    if stack.outputs is None:
        return "n/a"
    for obj in stack.outputs:
        if 'instanceid' in obj['OutputKey'].lower():
            # print(obj['OutputValue'])
            return obj['OutputValue']
    return "n/a"


def get_public_ip_from_output(stack):
    if stack.outputs is None:
        return "n/a"
    for obj in stack.outputs:
        if 'publicip' in obj['OutputKey'].lower():
            # print(obj['OutputValue'])
            return obj['OutputValue']
    return 'n/a'


def get_creator(stack):
    for obj in (stack.tags or []):
        if 'creator' == obj['Key'].lower():
            return obj['Value']
    return None


def get_image_name_from_output(stack):
    if stack.outputs is None:
        return "n/a"
    for obj in stack.outputs:
        if 'imagename' in obj['OutputKey'].lower():
            return obj['OutputValue']
    return 'n/a'


@click.group(help="Utils for CloudFormation")
def cf():
    pass


@click.command(help="Delete Stacks")
@click.argument("stack-name")
@click.pass_context
def delete_stack(ctx, stack_name):
    click.echo(f"Deleting [{stack_name}] ...")
    logger.info(f"Deleting [{stack_name}] ...")
    boto3.resource('cloudformation').Stack(stack_name).delete()
    ctx.invoke(ls_stacks, all=False)


@click.command(help="List Stacks")
@click.option("--all", is_flag=True, help='List all stack (include ones not created by me)')
def ls_stacks(all):
    resource = boto3.resource('cloudformation')
    stacks = list(resource.stacks.all())
    data = [
        [
            truncate(stack.name, 35),
            get_instance_id_from_output(stack),
            get_public_ip_from_output(stack),
            # get_private_ip_from_output(stack),
            stack.stack_status,
            # get_image_name_from_output(stack),
            # stack.stack_status_reason,
            get_creator(stack),
        ] for stack in stacks]
    if not all:
        data = [d for d in data if 'haoru' in d]
    print(tabulate(data,
                   headers=['Name',
                            "Instance ID",
                            'Public IP',
                            # 'Private IP',
                            'Status',
                            # 'Image',
                            # 'Reason'
                            'Creator',
                            ]))


cf.add_command(ls_stacks)
cf.add_command(delete_stack)
