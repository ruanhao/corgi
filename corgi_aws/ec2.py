import click
import logging
import boto3
from tabulate import tabulate

ec2_client = boto3.client('ec2')
logger = logging.getLogger(__name__)

@click.group(help="Utils for EC2")
def ec2():
    pass


@ec2.command(help="List CBD Images")
def ls_cbd_images():
    images = ec2_client.describe_images(
        Owners=['self'],
        Filters=[
            {
                'Name': 'name',
                'Values': ['Cisco*']
            }])['Images']
    data = [[image['CreationDate'], image['ImageId'], image['Name']]
            for image in images]

    print(tabulate(data, headers=['CreateDate', 'Image', 'Name']))
