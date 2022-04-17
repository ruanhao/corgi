import boto3
import logging

logger = logging.getLogger(__name__)


def check_aws_credential():
    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()
    region_name = session.region_name
    access_key = creds.access_key
    secret_key = creds.secret_key
    bye = False
    if not region_name:
        bye = True
        print("Please specify env variable AWS_DEFAULT_REGION")
    if not access_key:
        bye = True
        print("Please specify env variable AWS_ACCESS_KEY_ID")
    if not secret_key:
        bye = True
        print("Please specify env variable AWS_SECRET_ACCESS_KEY")
    if bye:
        exit(0)
    logger.info(f"AWS_DEFAULT_REGION: {region_name}")
    logger.info(f"AWS_ACCESS_KEY_ID: {access_key}")
    logger.info(f"AWS_SECRET_ACCESS_KEY: {secret_key}")


def default_vpc_id():
    vpc = boto3.client('ec2').describe_vpcs(
        Filters=[
            {
                'Name': 'isDefault',
                'Values': ["true"]
            }
        ]
    )['Vpcs'][0]
    return vpc['VpcId']


def subnet_id(vpc_id=None, index=0):
    if vpc_id is None:
        vpc_id = default_vpc_id()

    return boto3.client('ec2').describe_subnets(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ]
    )['Subnets'][index]['SubnetId']


def latest_linux2_ami():
    response = boto3.client('ec2').describe_images(
            Filters=[
                {
                    'Name': 'name',
                    # 'Values': ['amzn2-ami-hvm-2.0.????????-x86_64-gp2']
                    'Values': ['amzn2-ami-hvm-2.0.????????.?-x86_64-gp2']
                },

                {
                    'Name': 'state',
                    'Values': ['available']
                }
            ],
            Owners=['amazon'],
        )
    return sorted(response['Images'],
                  key=lambda img: img.get('CreationDate'))[-1]['ImageId']


def ami_name(ami):
    return boto3.client('ec2').describe_images(ImageIds=[ami])['Images'][0]['Name']
