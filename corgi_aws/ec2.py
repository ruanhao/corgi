import click
import logging
import boto3
from sys import platform
from tabulate import tabulate
from corgi_common.loggingutils import info, fatal
from corgi_common.dsutils import flatten
from corgi_common.dateutils import YmdHMS
from corgi_common import goodbye
from .common import (
    default_vpc_id,
    subnet_id,
    latest_linux2_ami,
    ami_name,
    cf_template,
)
import subprocess
from troposphere import Ref, Output, Tags, Parameter, GetAtt, Equals, Sub, And
from troposphere.ec2 import (
    SecurityGroup,
    SecurityGroupRule,
    Instance,
    Volume,
    VolumeAttachment,
    NetworkInterfaceProperty,
    BlockDeviceMapping,
    EBSBlockDevice
)


ec2_client = boto3.client('ec2')
cf_client = boto3.client('cloudformation')
logger = logging.getLogger(__name__)

def assert_no_name_collision(stack_name):
    try:
        boto3.resource('cloudformation').Stack(stack_name).stack_id
    except Exception:
        return
    fatal(f"Stack [{stack_name}] already exists")


def decide_username(imageName):
    imageName = imageName.lower()
    if "cisco" in imageName or 'findit' in imageName:
        return 'cisco'
    if "ubuntu" in imageName:
        return 'ubuntu'
    return 'ec2-user'


def key_find(lst, key, value):
    return next((item for item in lst if item[key] == value), None)


def run_script(script):
    proc = subprocess.Popen(['bash', '-c', script],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode:
        click.echo(f"[{proc.returncode}]: {stderr}", err=True)
    return stdout


def write_to_clipboard(output):
    process = subprocess.Popen('pbcopy', env={'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE)
    process.communicate(output.encode())


@click.group(help="Utils for EC2")
def ec2():
    pass

@ec2.command(help="Launch AWS Instance")
@click.option("--image-id", '-i')
@click.option("--stack-name", '-s', required=True)
@click.option("--instance-num", "-n", "instance_num", help="Number of EC2 instance", default=1, type=int, show_default=True)
@click.option('--instance-type', default='c5d.xlarge', show_default=True)
@click.option('--volume-size', type=int, default=80, help='Boot Ebs volume size (GB)', show_default=True)
@click.option('--keyname', required=True, envvar="AWS_KEYPAIR", help='Key name to ssh with')
@click.option('--add-volume', is_flag=True, help='Add additional volume', show_default=True)
@click.option('--add-ephemeral', is_flag=True, help='Add instance store', hidden=True)  # seems instance store is decided by instance type
@click.option('--dry', is_flag=True)
@click.option('--json', 'json_format', is_flag=True)
def launch_instance(
        image_id,
        stack_name,
        instance_num,
        instance_type,
        volume_size,
        keyname,
        dry,
        json_format,
        add_volume,
        add_ephemeral
):
    stack_name += YmdHMS()
    parameters = [
        Parameter(
            "KeyName",
            Description="Name of an existing EC2 KeyPair to enable SSH access to the instance",
            Type="AWS::EC2::KeyPair::KeyName",
        ),
        Parameter(
            "VPCId",
            Type="AWS::EC2::VPC::Id",
            Description="VPC ID",
        ),
        Parameter(
            "SubnetId",
            Type="AWS::EC2::Subnet::Id",
            Description="VPC subnet ID.",
        ),
        Parameter(
            "InstanceType",
            Default="c5d.xlarge",
            Type="String",
            # AllowedValues=["t2.micro", "c5.xlarge"],
            ConstraintDescription="Must be a valid EC2 instance type.",
        ),
        Parameter(
            "ImageId",
            Type="String",
            Description='Image ID',
        ),
        Parameter(
            "AttachVolume",
            Description='Should the volume be attached?',
            Type='String',
            Default='yes',
            AllowedValues=['yes', 'no']
        ),
        Parameter(
            "AdditionalVolume",
            Description='Add one more volume?',
            Type='String',
            Default='yes' if add_volume else 'no',
            AllowedValues=['yes', 'no']
        ),
    ]

    conditions = {
        'ShouldAddVolume': Equals(Ref('AdditionalVolume'), 'yes'),
        'ShouldAttach': And(Equals(Ref('AttachVolume'), 'yes'), Equals(Ref('AdditionalVolume'), 'yes')),
    }

    security_group = SecurityGroup(
        "SecurityGroup",
        GroupDescription=f"In stack {stack_name}",
        VpcId=Ref('VPCId'),
        Tags=Tags(
            Name=Ref("AWS::StackName"),
        ),
        SecurityGroupIngress=[
            SecurityGroupRule(
                IpProtocol='icmp',
                CidrIp='0.0.0.0/0',
                FromPort=-1,  # -1 means every port
                ToPort=-1
            ),
            SecurityGroupRule(
                IpProtocol='tcp',
                CidrIp='0.0.0.0/0',
                FromPort=1,
                ToPort=65535
            ),
            SecurityGroupRule(
                IpProtocol='udp',
                CidrIp='0.0.0.0/0',
                FromPort=1,
                ToPort=65535
            ),
        ]
    )

    instances = flatten([
        [
            Instance(
                f'Instance{i}',
                KeyName=Ref('KeyName'),
                InstanceType=Ref('InstanceType'),
                ImageId=Ref('ImageId'),
                Tags=Tags(
                    Name=Ref("AWS::StackName"),
                    Environment="NoProd",
                    ResourceOwner="haoru"
                ),
                BlockDeviceMappings=flatten([
                    BlockDeviceMapping(
                        # boot volume should be /dev/xvda, others could be in the range of /dev/xvdf to /dev/xvdp
                        DeviceName="/dev/xvda",  # boot block device
                        Ebs=EBSBlockDevice(DeleteOnTermination=False, Encrypted=False, VolumeSize=volume_size),
                    ),
                    [BlockDeviceMapping(
                        DeviceName="/dev/xvdb",
                        VirtualName='ephemeral0',  # instance store
                    )] if add_ephemeral else [],
                ]),
                NetworkInterfaces=[
                    NetworkInterfaceProperty(
                        AssociatePublicIpAddress=True,
                        DeviceIndex=0,
                        DeleteOnTermination=True,
                        GroupSet=[Ref('SecurityGroup')],
                        SubnetId=Ref('SubnetId')
                    ),
                    # NetworkInterfaceProperty(
                    #     DeviceIndex=1,
                    #     DeleteOnTermination=True,
                    #     GroupSet=[Ref('SecurityGroup')],
                    #     SubnetId=Ref('SubnetId')
                    #     SecondaryPrivateIpAddressCount=secondary_ip_count
                    # ),
                ]
            ),
            Volume(             # additional volume
                f"Volume{i}",
                AvailabilityZone=Sub(f"${{Instance{i}.AvailabilityZone}}"),
                Encrypted=False,
                Size=int(volume_size * 1.5),
                VolumeType='gp2',
                Tags=Tags(
                    Name=Ref("AWS::StackName"),
                ),
                Condition='ShouldAddVolume',
            ),
            VolumeAttachment(
                f'VolumeAttachment{i}',
                Device='/dev/xvdf',
                InstanceId=Ref(f'Instance{i}'),
                VolumeId=Ref(f'Volume{i}'),
                Condition="ShouldAttach",
            ),
        ] for i in range(instance_num)
    ])
    outputs = flatten([
        [
            Output(
                f"InstanceId{idx}",
                Description=f"InstanceId of the newly created EC2 instance ({idx})",
                Value=Ref(f'Instance{idx}'),
            ),
            Output(
                f"PublicIP{idx}",
                Description=f"Public IP address of the newly created EC2 instance ({idx})",
                Value=GetAtt(f'Instance{idx}', "PublicIp"),
            ),
            Output(
                f"PrivateIP{idx}",
                Description=f"Private IP address of the newly created EC2 instance ({idx})",
                Value=GetAtt(f'Instance{idx}', "PrivateIp"),
            )
        ] for idx in range(instance_num)])

    t = cf_template(
        parameters=parameters,
        outputs=outputs,
        resources=[security_group, *instances],
        conditions=conditions
    )
    if dry:
        if json_format:
            print(t.to_json())
        else:
            print(t.to_yaml())
        goodbye()

    assert_no_name_collision(stack_name)
    vpc_id = default_vpc_id()
    info(f"Default VPC: {vpc_id}")
    the_subnet_id = subnet_id(vpc_id)  # first subnet in VPC
    info(f"Subnet ID: {the_subnet_id}")
    if not image_id:
        image_id = latest_linux2_ami()
    image_name = ami_name(image_id)
    info(f'AMI: {image_id} ({image_name})')
    username = decide_username(image_name)
    info(f"Selected username: {username}")
    info(f"Creating stack [{stack_name}] ...")
    cf_client.create_stack(
        StackName=stack_name,
        TemplateBody=t.to_yaml(),
        Tags=[{'Key': 'creator', 'Value': 'haoru'}],
        Parameters=[
            {'ParameterKey': 'KeyName', 'ParameterValue': keyname},
            {'ParameterKey': 'VPCId', 'ParameterValue': vpc_id},
            {'ParameterKey': 'SubnetId', 'ParameterValue': the_subnet_id},
            {'ParameterKey': 'InstanceType', 'ParameterValue': instance_type},
            {'ParameterKey': 'ImageId', 'ParameterValue': image_id},
        ]
    )
    info("Waiting for completion ...")
    cf_client.get_waiter('stack_create_complete').wait(StackName=stack_name)
    outputs = cf_client.describe_stacks(StackName=stack_name)['Stacks'][0]['Outputs']
    instances_info = [
        {
            'instance_id': key_find(outputs, 'OutputKey', f'InstanceId{i}')['OutputValue'],
            'public_ip': key_find(outputs, 'OutputKey', f'PublicIP{i}')['OutputValue'],
            'private_ip': key_find(outputs, 'OutputKey', f'PrivateIP{i}')['OutputValue'],
        } for i in range(instance_num)
    ]

    for idx, instance_info in enumerate(instances_info):
        instance_id = instance_info['instance_id']
        public_ip = instance_info['public_ip']
        private_ip = instance_info['private_ip']
        info(f"Instance{idx} ID: {instance_id}, public IP: {public_ip}, Private IP: {private_ip} (ssh {username}@{public_ip})")
        # sshStringJump = f'ssh -J ec2-user@3.211.99.203 {username}@{private_ip}'

    if platform == 'darwin':    # only save ssh config for the first instance
        public_ip_for_first_instance = instances_info[0]['public_ip']
        run_script(f"""storm delete {stack_name} || true""")
        run_script(f"""storm add {stack_name} {username}@{public_ip_for_first_instance}""")
        write_to_clipboard(f"ssh {stack_name}")


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
