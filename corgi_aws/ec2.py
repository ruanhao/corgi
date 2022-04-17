import click
import logging
import boto3
from sys import platform
from tabulate import tabulate
from .common import (
    default_vpc_id,
    subnet_id,
    latest_linux2_ami,
    ami_name
)
import subprocess
from troposphere import Template, Ref, Output, Tags, GetAtt
from troposphere.ec2 import (
    SecurityGroup,
    # SecurityGroupIngress,
    SecurityGroupRule,
    Instance,
    NetworkInterfaceProperty,
    BlockDeviceMapping,
    EBSBlockDevice
)


ec2_client = boto3.client('ec2')
cf_client = boto3.client('cloudformation')
logger = logging.getLogger(__name__)


def fatal(msg):
    logger.critical(msg)
    click.echo(msg, err=True)
    raise click.Abort()


def info(msg):
    logger.info(msg)
    click.echo(msg)


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


@click.command(help="Launch AWS Instance")
@click.option("--image-id", '-i')
@click.option("--stack-name", '-s', required=True)
@click.option("--instance-num", "-n", "instance_num", help="Number of EC2 instance", default=1, type=int)
@click.option('--instance-type',  default='c5.xlarge')
@click.option('--volume', type=int, default=60)
@click.option('--keypair', required=True, envvar="AWS_KEYPAIR", help='Use a key pair to securely connect instance')
def launch_instance(image_id, stack_name, instance_num, instance_type, volume, keypair):
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
    info(f"Number of instance(s): {instance_num}")
    info(f"Selected username: {username}")

    security_group_name = f"SecurityGroupForStack{stack_name}"

    t = Template()

    security_group_rules = []
    security_group_rules.append(SecurityGroupRule(
        IpProtocol='icmp',
        CidrIp='0.0.0.0/0',
        FromPort=-1,  # -1 means every port
        ToPort=-1
    ))
    security_group_rules.append(SecurityGroupRule(
        IpProtocol='tcp',
        CidrIp='0.0.0.0/0',
        FromPort=1,
        ToPort=65535
    ))
    sg = t.add_resource(SecurityGroup(
        security_group_name,
        GroupDescription=f"used in stack {stack_name}",
        VpcId=vpc_id,
        SecurityGroupIngress=security_group_rules,
    ))

    instances = []
    # add instance
    for i in range(instance_num):
        instance = t.add_resource(Instance(
            f"Instance{i}",
            KeyName=keypair,
            InstanceType=instance_type,
            ImageId=image_id,
            NetworkInterfaces=[
                NetworkInterfaceProperty(
                    AssociatePublicIpAddress=True,
                    DeviceIndex=0,
                    DeleteOnTermination=True,
                    GroupSet=[Ref(sg)],
                    SubnetId=the_subnet_id
                ),
                # NetworkInterfaceProperty(
                #     DeviceIndex=1,
                #     DeleteOnTermination=True,
                #     GroupSet=[Ref(sg)],
                #     SubnetId=subnet_id,
                #     SecondaryPrivateIpAddressCount=secondary_ip_count
                # ),
            ],
            Tags=Tags(
                Name=f"{stack_name}",
                Application=Ref("AWS::StackName"),
                Developer="cisco::haoru",
                DataClassification="Cisco Highly Confidential",
                Environment="NoProd",
                DataTaxonomy="Administrative Data",
                ApplicationName=Ref("AWS::StackName"),
                CiscoMailAlias='haoru@cisco.com',
                ResourceOwner="haoru"
            ),
            BlockDeviceMappings=[
                # BlockDeviceMapping(DeviceName="/dev/sda1", Ebs=EBSBlockDevice(DeleteOnTermination=False, Encrypted=False, VolumeSize=60))
                BlockDeviceMapping(DeviceName="/dev/xvda", Ebs=EBSBlockDevice(DeleteOnTermination=False, Encrypted=False, VolumeSize=volume))
            ]
        ))
        instances.append(instance)  # 保存 instance 引用
    for idx, ins in enumerate(instances):
        t.add_output([
            Output(
                f"InstanceId{idx}",
                Description=f"InstanceId of the newly created EC2 instance ({idx})",
                Value=Ref(ins),
            ),
            Output(
                f"PublicIP{idx}",
                Description=f"Public IP address of the newly created EC2 instance ({idx})",
                Value=GetAtt(ins, "PublicIp"),
            ),
            Output(
                f"PrivateIP{idx}",
                Description=f"Private IP address of the newly created EC2 instance ({idx})",
                Value=GetAtt(ins, "PrivateIp"),
            ),
            Output(
                "ImageName",
                Description="Image Name",
                Value=image_name
            ),

        ])

    t.add_output([
        Output(
            security_group_name,
            Description=f"Security Group In Stack {stack_name}",
            Value=Ref(sg),
        )
    ])
    cf_client.create_stack(
        StackName=stack_name,
        TemplateBody=t.to_yaml(),
        Tags=[{'Key': 'creator', 'Value': 'haoru'}]
    )
    info(f"Creating stack [{stack_name}] ...")
    cf_client.get_waiter('stack_create_complete').wait(StackName=stack_name)
    info("Stack creation completed")
    click.echo("===========")
    outputs = cf_client.describe_stacks(StackName=stack_name)['Stacks'][0]['Outputs']
    instances_info = []
    for i in range(len(instances)):
        instances_info.append({
            'instance_id': key_find(outputs, 'OutputKey', f'InstanceId{i}')['OutputValue'],
            'public_ip': key_find(outputs, 'OutputKey', f'PublicIP{i}')['OutputValue'],
            'private_ip': key_find(outputs, 'OutputKey', f'PrivateIP{i}')['OutputValue'],
        })

    for instance_info in instances_info:
        instance_id = instance_info['instance_id']
        public_ip = instance_info['public_ip']
        private_ip = instance_info['private_ip']
        info(f"Instance ID: {instance_id}, public IP: {public_ip}, Private IP: {private_ip}")
        # sshStringJump = f'ssh -J ec2-user@3.211.99.203 {username}@{private_ip}'
        info(f"SSH Login: ssh {username}@{public_ip}")
        if platform == 'darwin':
            run_script(f"""storm delete {stack_name} || true""")
            run_script(f"""storm add {stack_name} {username}@{public_ip}""")
            write_to_clipboard(f"ssh {stack_name}")


@click.command(help="List CBD Images")
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


ec2.add_command(ls_cbd_images)
ec2.add_command(launch_instance)
