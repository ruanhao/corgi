import click
import logging
import boto3
from tabulate import tabulate
from .common import Regions
from corgi_common import pretty_print

ec2_client = boto3.client('ec2')
logger = logging.getLogger(__name__)

def _regions():
    return [r['RegionName'] for r in ec2_client.describe_regions()['Regions']]

def _region_location_mapping():
    regions = Regions.get_regions()
    return {item['code']: item['name'] for item in regions}

@click.group(help="Utils for EC2")
def ec2():
    pass

@ec2.command(help="Show AZ info for regions")
@click.option('--region-names', '-r')
def describe_availability_zones(region_names):
    mapping = _region_location_mapping()
    regions = region_names.split(',') if region_names else _regions()
    result = []
    for region in regions:
        zones = boto3.client('ec2', region_name=region).describe_availability_zones()['AvailabilityZones']
        zone_names = [z['ZoneName'] for z in zones]
        location = mapping.get(region, 'n/a')
        result.append({'region': '/'.join([region, location, str(len(zones))]), 'zones': ' '.join(zone_names)})
    pretty_print(sorted(result, key=lambda o: o['region'], reverse=True), mappings={
        'Region': 'region',
        'AZs': 'zones'
    })


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
