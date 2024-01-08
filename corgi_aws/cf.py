import click
import logging
from corgi_common.dsutils import flatten
from corgi_common.loggingutils import info, fatal
from corgi_common.scriptutils import run_script, write_to_clipboard
from corgi_common.jinja2utils import get_rendered
import boto3
from tabulate import tabulate
from corgi_common import goodbye
from troposphere import Ref, Output, Tags, Parameter, GetAtt, Equals, Sub, And, Base64
from troposphere.efs import FileSystem, MountTarget
from troposphere.policies import CreationPolicy, ResourceSignal
from troposphere.ec2 import (
    SecurityGroup,
    SecurityGroupRule,
    Instance,
    Volume,
    VolumeAttachment,
    NetworkInterfaceProperty,
    BlockDeviceMapping,
    EBSBlockDevice,
    EIP,
    EIPAssociation,
)
from .common import (
    default_vpc_id,
    decide_username,
    subnet_id,
    latest_linux2_ami,
    ami_name,
    cf_template,
)
from sys import platform

ec2_client = boto3.client('ec2')
cf_client = boto3.client('cloudformation')

logger = logging.getLogger(__name__)


def key_find(lst, key, value):
    return next((item for item in lst if item[key] == value), None)

def assert_no_name_collision(stack_name):
    try:
        boto3.resource('cloudformation').Stack(stack_name).stack_id
    except Exception:
        return
    fatal(f"Stack [{stack_name}] already exists")

def _user_data(**values):
    return get_rendered('user-data.j2', **values)

def truncate(s, limit=30):
    return (s[:limit] + '..') if len(s) > limit else s


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


@cf.command(help="Delete Stacks")
@click.argument("stack-name")
@click.pass_context
def delete_stack(ctx, stack_name):
    click.echo(f"Deleting [{stack_name}] ...")
    logger.info(f"Deleting [{stack_name}] ...")
    boto3.resource('cloudformation').Stack(stack_name).delete()
    ctx.invoke(ls_stacks, all=False)


@cf.command(help="List Stacks")
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


@cf.command(help="Launch AWS Instance(s)")
@click.option("--image-id", '-i')
@click.option("--stack-name", '-s', required=True)
@click.option("--instance-num", "-n", "instance_num", help="Number of EC2 instance", default=1, type=int, show_default=True)
@click.option('--instance-type', default='c5d.xlarge', show_default=True)
@click.option('--volume-size', type=int, default=80, help='Boot Ebs volume size (GB)', show_default=True)
@click.option('--keyname', required=True, envvar="AWS_KEYPAIR", help='Key name to ssh with (env: AWS_KEYPAIR)', show_default=True)
@click.option('--add-volume', is_flag=True, help='Add additional volume', show_default=True)
@click.option('--add-ephemeral', is_flag=True, help='Add instance store', hidden=True)  # seems instance store is decided by instance type
@click.option('--dry', is_flag=True)
@click.option('--with-eip', is_flag=True, help='Associate EIP to the instance', show_default=True)
@click.option('--debug', is_flag=True)
@click.option('--efs', is_flag=True)
@click.option('--ingress-ports')
@click.option('--json', 'json_format', is_flag=True)
def launch_instances(
        debug,
        image_id,
        efs,
        stack_name,
        instance_num,
        instance_type,
        volume_size,
        keyname,
        dry,
        json_format,
        add_volume,
        with_eip,
        add_ephemeral,
        ingress_ports
):
    # stack_name += YmdHMS()
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

    additional_ingress_rules = []
    for port in [22, 443, 80]:
        additional_ingress_rules.append(
            SecurityGroupRule(
                IpProtocol='tcp',
                CidrIp='0.0.0.0/0',
                FromPort=port,
                ToPort=port
            )
        )

    if ingress_ports:
        for port in ingress_ports.split(","):
            port = int(port.strip())
            additional_ingress_rules.append(
                SecurityGroupRule(
                    IpProtocol='tcp',
                    CidrIp='0.0.0.0/0',
                    FromPort=port,
                    ToPort=port
                )
            )

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
            # SecurityGroupRule(
            #     IpProtocol='tcp',
            #     CidrIp='0.0.0.0/0',
            #     FromPort=1,
            #     ToPort=65535
            # ),
            # SecurityGroupRule(
            #     IpProtocol='udp',
            #     CidrIp='0.0.0.0/0',
            #     FromPort=1,
            #     ToPort=65535
            # ),
            *additional_ingress_rules
        ]
    )

    efs_resources = []
    if efs:
        efs_resources = [
            FileSystem(
                "FileSystem",
                FileSystemTags=Tags(Name=Ref("AWS::StackName")),
            ),
            SecurityGroup(
                'EFSClientSecurityGroup',
                GroupDescription='for EFS Mount target client',
                VpcId=Ref('VPCId'),
                Tags=Tags(
                    Name=Ref("AWS::StackName"),
                ),
            ),
            SecurityGroup(
                'MountTargetSecurityGroup',
                GroupDescription='for EFS Mount target',
                VpcId=Ref('VPCId'),
                Tags=Tags(
                    Name=Ref("AWS::StackName"),
                ),
                SecurityGroupIngress=[
                    SecurityGroupRule(
                        FromPort=2049,
                        IpProtocol='tcp',
                        SourceSecurityGroupId=Ref('EFSClientSecurityGroup'),
                        ToPort=2049,
                    )
                ]
            ),
            MountTarget(
                'MountTarget',
                FileSystemId=Ref('FileSystem'),
                SecurityGroups=[Ref('MountTargetSecurityGroup')],
                SubnetId=Ref('SubnetId'),
            )
        ]

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
                        Ebs=EBSBlockDevice(DeleteOnTermination=True, Encrypted=False, VolumeSize=volume_size),
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
                        GroupSet=flatten([Ref('SecurityGroup'), Ref('EFSClientSecurityGroup') if efs else []]),
                        SubnetId=Ref('SubnetId')
                    ),
                    # NetworkInterfaceProperty(
                    #     DeviceIndex=1,
                    #     DeleteOnTermination=True,
                    #     GroupSet=[Ref('SecurityGroup')],
                    #     SubnetId=Ref('SubnetId')
                    #     SecondaryPrivateIpAddressCount=secondary_ip_count
                    # ),
                ],
                UserData=Base64(Sub(_user_data(instance_id=f'Instance{i}', efs=efs, debug=debug))),
                CreationPolicy=CreationPolicy(
                    ResourceSignal=ResourceSignal(Timeout="PT15M")
                ),
                DependsOn=['MountTarget'] if efs else [],
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

    eips = [
        EIP(
            f"EIP{i}",
            Domain="vpc",
        )
        for i in range(instance_num)
    ]

    eip_associations = [
        EIPAssociation(
            f"EIPAssociation{i}",
            AllocationId=GetAtt(f'EIP{i}', 'AllocationId'),
            InstanceId=Ref(f'Instance{i}'),
        )
        for i in range(instance_num)
    ]

    outputs = flatten([
        [
            Output(
                f"InstanceId{idx}",
                Description=f"InstanceId of the newly created EC2 instance ({idx})",
                Value=Ref(f'Instance{idx}'),
            ),
            Output(
                f"EIP{idx}",
                Description=f"EIP of the newly created EC2 instance ({idx})",
                Value=GetAtt(f'EIP{idx}', 'PublicIp'),
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
        resources=[security_group, *instances, *efs_resources, *eips, *eip_associations],
        conditions=conditions
    )
    if dry:
        if json_format:
            print(t.to_json())
        else:
            print(t.to_yaml(clean_up=True))
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
        TemplateBody=t.to_yaml(clean_up=True),
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
