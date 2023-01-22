import click
import logging
import boto3
from tabulate import tabulate
from .common import Regions
from corgi_common import pretty_print, utc_to_local

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

@ec2.command(help="Show instances")
@click.option('--region', '-r', envvar='AWS_DEFAULT_REGION', default='us-east-1')
def instances(region):
    """
    ['ami_launch_index', 'architecture', 'attach_classic_link_vpc', 'attach_volume', 'block_device_mappings', 'boot_mode', 'capacity_reservation_id', 'capacity_reservation_specification', 'classic_address', 'client_token', 'console_output', 'cpu_options', 'create_image', 'create_tags', 'delete_tags', 'describe_attribute', 'detach_classic_link_vpc', 'detach_volume', 'ebs_optimized', 'elastic_gpu_associations', 'elastic_inference_accelerator_associations', 'ena_support', 'enclave_options', 'get_available_subresources', 'hibernation_options', 'hypervisor', 'iam_instance_profile', 'id', 'image', 'image_id', 'instance_id', 'instance_lifecycle', 'instance_type', 'ipv6_address', 'kernel_id', 'key_name', 'key_pair', 'launch_time', 'licenses', 'load', 'maintenance_options', 'meta', 'metadata_options', 'modify_attribute', 'monitor', 'monitoring', 'network_interfaces', 'network_interfaces_attribute', 'outpost_arn', 'password_data', 'placement', 'placement_group', 'platform', 'platform_details', 'private_dns_name', 'private_dns_name_options', 'private_ip_address', 'product_codes', 'public_dns_name', 'public_ip_address', 'ramdisk_id', 'reboot', 'reload', 'report_status', 'reset_attribute', 'reset_kernel', 'reset_ramdisk', 'reset_source_dest_check', 'root_device_name', 'root_device_type', 'security_groups', 'source_dest_check', 'spot_instance_request_id', 'sriov_net_support', 'start', 'state', 'state_reason', 'state_transition_reason', 'stop', 'subnet', 'subnet_id', 'tags', 'terminate', 'tpm_support', 'unmonitor', 'usage_operation', 'usage_operation_update_time', 'virtualization_type', 'volumes', 'vpc', 'vpc_addresses', 'vpc_id', 'wait_until_exists', 'wait_until_running', 'wait_until_stopped', 'wait_until_terminated']
    """
    ec2 = boto3.resource('ec2', region_name=region)
    instances = list(ec2.instances.all())
    # import pdir
    # image = instances[0].image

    def __image_name(image):
        try:
            return image.name
        except Exception:
            return image.id
    # print(type(image))
    # print(dir(image))
    # print(image.name)

    def __tag_name(tags):
        if not tags:
            return ''
        for tag in tags:
            if tag['Key'].lower() == 'name':
                return tag['Value']
        return ''

    pretty_print(instances, mappings={
        'ID': ('', lambda i: i.id),
        'Name': ('', lambda i: __tag_name(i.tags)),
        'State': ('', lambda i: i.state['Name']),
        'Public IP': ('', lambda i: i.public_ip_address),
        'Launch Time': ('', lambda i: utc_to_local(i.launch_time)),
        'Type': ('', lambda i: i.instance_type),
        # 'Image': ('', lambda i: __image_name(i.image)),
        'AMI': ('', lambda i: i.image_id),
    })

@ec2.command(help="Show keypairs")
@click.option('--region', '-r', envvar='AWS_DEFAULT_REGION', default='us-east-1')
def keypairs(region):
    client = boto3.client('ec2', region)
    keypairs = client.describe_key_pairs().get('KeyPairs', [])
    pretty_print(keypairs, mappings={
        'ID': 'KeyPairId',
        'Name': 'KeyName',
        'Type': 'KeyType',
        'CreateTime': ('CreateTime', utc_to_local),
    })

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
@click.option('--release', is_flag=True)
def ls_cbd_images(release):
    images = ec2_client.describe_images(
        Owners=['self'],
        Filters=[
            {
                'Name': 'name',
                'Values': ['Cisco*']
            }])['Images']
    # from pprint import pprint
    # pprint(images)
    snapshots = []
    releases = []
    for image in images:
        result = snapshots
        if 'Tags' in image:
            result = releases
        result.append([image['CreationDate'], image['ImageId'], image['Name']])

    data = releases if release else snapshots
    print(tabulate(data, headers=['CreateDate', 'Image', 'Name']))
