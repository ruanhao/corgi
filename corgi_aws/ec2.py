import click
import logging
import boto3
from tabulate import tabulate
from .common import Regions
from corgi_common import pretty_print, utc_to_local

ec2_client = boto3.client('ec2')
client = ec2_client
logger = logging.getLogger(__name__)

def _regions():
    return [r['RegionName'] for r in ec2_client.describe_regions()['Regions']]

def _region_location_mapping():
    regions = Regions.get_regions()
    return {item['code']: item['name'] for item in regions}

@click.group(help="Utils for EC2")
@click.pass_context
@click.option("--dry", is_flag=True)
@click.option('--region', '-r', envvar='AWS_DEFAULT_REGION', default='us-east-1')
def ec2(ctx, region, dry):
    ctx.ensure_object(dict)
    ctx.obj['dry'] = dry
    ctx.obj['region'] = region
    pass

@ec2.group(help='[group] snapshot utils')
@click.pass_context
def snapshot(ctx):
    pass

@ec2.group(help='[group] image utils')
@click.pass_context
def image(ctx):
    pass

def _snapshots(token=''):
    response = client.describe_snapshots(
        OwnerIds=['self'],
        MaxResults=1000,
        NextToken=token
    )
    snapshots = response['Snapshots']
    if response.get('NextToken'):
        snapshots += _snapshots(response['NextToken'])
    return snapshots

def _volumes(snapshot_id, token=''):
    response = client.describe_volumes(
        Filters=[
            {
                'Name': 'snapshot-id',
                'Values': [snapshot_id]
            }
        ],
        MaxResults=1000,
        NextToken=token
    )
    volumes = response['Volumes']
    if response.get('NextToken'):
        volumes += _volumes(snapshot_id, response['NextToken'])
    return volumes

@snapshot.command(short_help='clear useless snapshot/volume')
@click.pass_context
def clear(ctx):
    snapshots = _snapshots()
    print(f"found {len(snapshots)} snapshots")
    deleted = []
    for snapshot in snapshots:
        snapshot_id = snapshot['SnapshotId']
        volumes = _volumes(snapshot_id)
        in_use_volumes = []
        if volumes:
            for volume in volumes:
                volume_id = volume['VolumeId']
                if volume['State'] == 'in-use':
                    print(f"  skipping volume {volume_id} in-use")
                    in_use_volumes.append(volume_id)
                else:
                    print(f"  deleting volume {volume_id}, tags:{volume.get('Tags')} ...")
                    if not ctx.obj['dry']:
                        response = client.delete_volume(VolumeId=volume_id, DryRun=ctx.obj['dry'])
                        logger.info(f"delete volume response:{response}")
                    print(f"  volume ({volume_id}) deleted (dry:{ctx.obj['dry']})")
        if not in_use_volumes or snapshot['State'] != 'in-use':
            if not ctx.obj['dry']:
                try:
                    response = client.delete_snapshot(SnapshotId=snapshot_id)
                    logger.info(f"delete snapshot {snapshot_id} response:{response}")
                except Exception as e:
                    if 'currently in use by ami' in str(e):
                        print(f"skipping snapshot {snapshot_id} in-use by AMI")
                        continue
                    else:
                        e.print_stack()
            print(f"snapshot ({snapshot_id}) deleted, state:{snapshot['State']}, tags:{snapshot.get('Tags')} (dry:{ctx.obj['dry']})")
            deleted.append(snapshot_id)
    if deleted:
        print(f"deleted {len(deleted)} snapshots:{deleted}")
    else:
        print("no snapshot deleted")
    pass

@snapshot.command(short_help='apply snapshot to instance')
@click.pass_context
@click.option("--instance-id", '-i', required=True)
@click.option("--snapshot-id", '-s', required=True)
def apply(ctx, instance_id, snapshot_id):
    print(f"stopping instance {instance_id} ...")
    response = ec2_client.stop_instances(
        InstanceIds=[instance_id]
    )
    logger.info(f"stop_instances response:{response}")
    waiter = ec2_client.get_waiter('instance_stopped')
    print("waiting for ready ...")
    waiter.wait(InstanceIds=[instance_id])

    response = client.describe_instances(InstanceIds=[instance_id])
    instance = response['Reservations'][0]['Instances'][0]
    root_device_name = instance['RootDeviceName']

    # hprint(instance, as_json=True)

    device_mappings = ec2_client.describe_instance_attribute(InstanceId=instance_id, Attribute='blockDeviceMapping')['BlockDeviceMappings']
    volume_id = ([dm['Ebs']['VolumeId'] for dm in device_mappings if dm['DeviceName'] == root_device_name] or [None])[0]
    if volume_id:
        print(f"detaching volume {volume_id} ...")
        response = client.detach_volume(
            Force=True,
            InstanceId=instance_id,
            VolumeId=volume_id,
        )
        logger.info("detach volume response:{response}")

    print(f"creating volume from snapshot {snapshot_id} ...")
    response = client.create_volume(
        AvailabilityZone=instance['Placement']['AvailabilityZone'],
        SnapshotId=snapshot_id,
        TagSpecifications=[
            {
                'ResourceType': 'volume',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': f'created from snapshot {snapshot_id}'
                    },
                ]
            },
        ],
    )
    logger.info(f"create volume resonse:{response}")
    volume_id = response['VolumeId']
    print(f"volume created:{volume_id}")

    print("waiting for volume availability ...")
    waiter = client.get_waiter('volume_available')
    waiter.wait(VolumeIds=[volume_id])

    print(f"attaching volume {volume_id} to instance {instance_id} ...")
    response = client.attach_volume(
        Device=root_device_name,
        InstanceId=instance_id,
        VolumeId=volume_id,
    )
    logger.info(f"attach volume reponse:{response}")

    print(f"starting instance {instance_id} ...")
    response = ec2_client.start_instances(
        InstanceIds=[instance_id]
    )
    logger.info(f"start_instances response:{response}")
    waiter = ec2_client.get_waiter('instance_running')
    print("waiting for ready ...")
    waiter.wait(InstanceIds=[instance_id])

@snapshot.command(short_help='take snapshot')
@click.pass_context
@click.option("--instance-id", '-i', required=True)
@click.option("--mount-point", '-m', default='/dev/sda1', help='Root device name')
def create(ctx, instance_id, mount_point):
    device_mappings = ec2_client.describe_instance_attribute(InstanceId=instance_id, Attribute='blockDeviceMapping')['BlockDeviceMappings']
    volume_id = ([dm['Ebs']['VolumeId'] for dm in device_mappings if dm['DeviceName'] == mount_point] or [None])[0]
    assert volume_id, f"cannot find volume id, mapping:{device_mappings}"
    print(f"creating snapshot for volume {volume_id} ...")

    response = ec2_client.create_snapshot(
        Description=f'instance:{instance_id}, volume:{volume_id}, device:{mount_point}',
        # OutpostArn='string',
        VolumeId=volume_id,
        TagSpecifications=[
            {
                'ResourceType': 'snapshot',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': f'instance:{instance_id}, volume:{volume_id}, device:{mount_point}',
                    },
                ]
            },
        ],
        DryRun=ctx.obj['dry']
    )
    logger.info(f"create snapshot response:{response}")
    snapshot_id = response['SnapshotId']
    print(f"snapshot created: {snapshot_id}")

    waiter = ec2_client.get_waiter('snapshot_completed')
    print("waiting for snapshot ready ...")
    waiter.wait(
        SnapshotIds=[
            snapshot_id,
        ],
        DryRun=ctx.obj['dry']
    )
    print("done.")

    # while True:
    #     response = ec2_client.describe_snapshots(
    #         SnapshotIds=[snapshot_id],
    #         DryRun=ctx.obj['dry']
    #     )
    #     logger.info(f"describe snapshot response:{response}")
    #     snapshot = response['Snapshots'][0]
    #     if snapshot['State'] != 'completed':
    #         progress = snapshot['Progress']
    #         print(f"progress: {progress}")
    #         time.sleep(5)
    #     else:
    #         print("done")
    #         break


@ec2.command(help="Show instances")
@click.pass_context
def instances(ctx):
    """
    ['ami_launch_index', 'architecture', 'attach_classic_link_vpc', 'attach_volume', 'block_device_mappings', 'boot_mode', 'capacity_reservation_id', 'capacity_reservation_specification', 'classic_address', 'client_token', 'console_output', 'cpu_options', 'create_image', 'create_tags', 'delete_tags', 'describe_attribute', 'detach_classic_link_vpc', 'detach_volume', 'ebs_optimized', 'elastic_gpu_associations', 'elastic_inference_accelerator_associations', 'ena_support', 'enclave_options', 'get_available_subresources', 'hibernation_options', 'hypervisor', 'iam_instance_profile', 'id', 'image', 'image_id', 'instance_id', 'instance_lifecycle', 'instance_type', 'ipv6_address', 'kernel_id', 'key_name', 'key_pair', 'launch_time', 'licenses', 'load', 'maintenance_options', 'meta', 'metadata_options', 'modify_attribute', 'monitor', 'monitoring', 'network_interfaces', 'network_interfaces_attribute', 'outpost_arn', 'password_data', 'placement', 'placement_group', 'platform', 'platform_details', 'private_dns_name', 'private_dns_name_options', 'private_ip_address', 'product_codes', 'public_dns_name', 'public_ip_address', 'ramdisk_id', 'reboot', 'reload', 'report_status', 'reset_attribute', 'reset_kernel', 'reset_ramdisk', 'reset_source_dest_check', 'root_device_name', 'root_device_type', 'security_groups', 'source_dest_check', 'spot_instance_request_id', 'sriov_net_support', 'start', 'state', 'state_reason', 'state_transition_reason', 'stop', 'subnet', 'subnet_id', 'tags', 'terminate', 'tpm_support', 'unmonitor', 'usage_operation', 'usage_operation_update_time', 'virtualization_type', 'volumes', 'vpc', 'vpc_addresses', 'vpc_id', 'wait_until_exists', 'wait_until_running', 'wait_until_stopped', 'wait_until_terminated']
    """
    ec2 = boto3.resource('ec2', region_name=ctx.obj['region'])
    instances = list(ec2.instances.all())

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
@click.pass_context
def keypairs(ctx):
    client = boto3.client('ec2', ctx.obj['region'])
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


@image.command(help="filter images")
def filter():
    images = ec2_client.describe_images(
        Owners=['099720109477'],
        Filters=[
            {
                'Name': 'name',
                'Values': ['ubuntu/images/*ubuntu-jammy-22.04-amd64-server-*']
            },
            {
                'Name': 'virtualization-type',
                'Values': ['hvm']
            },
            {
                'Name': 'root-device-type',
                'Values': ['ebs']
            }
        ])['Images']
    snapshots = []
    for image in images:
        snapshots.append([image['CreationDate'], image['ImageId'], image['Name']])
    print(tabulate(snapshots, headers=['CreateDate', 'Image', 'Name']))


@image.command(short_help="share AMI with another account")
@click.option("--ami", "-i", required=True)
@click.option("--account", "-a", required=True, help='user ID')
@click.pass_context
def share(ctx, ami, account):
    image = client.describe_images(ImageIds=[ami])['Images'][0]
    # hprint(image)
    snapshot_ids = []
    for mapping in image['BlockDeviceMappings']:
        if 'Ebs' in mapping:
            snapshot_ids.append(mapping['Ebs']['SnapshotId'])
    # print(snapshot_ids)
    print(f"Sharing image with account {account} ...")
    client.modify_image_attribute(
        ImageId=ami,
        LaunchPermission={
            'Add': [
                {
                    'UserId': account,
                },
            ],
        },
    )

    for snapshot_id in snapshot_ids:
        print(f"Sharing snapshot {snapshot_id} with account {account} ...")
        client.modify_snapshot_attribute(
            Attribute='createVolumePermission',
            SnapshotId=snapshot_id,
            CreateVolumePermission={
                'Add': [
                    {
                        'UserId': account
                    },
                ],
            },
        )
