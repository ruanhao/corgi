import boto3
import logging
from troposphere import Template
from collections.abc import Iterable

ssm = boto3.client('ssm')

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

def _add_resources_to_template(t, items):
    if items and isinstance(items, Iterable):
        for item in items:
            t.add_resource(item)

def _add_outputs_to_template(t, items):
    if items and isinstance(items, Iterable):
        for item in items:
            t.add_output(item)


def _add_parameters_to_template(t, items):
    if items and isinstance(items, Iterable):
        for item in items:
            t.add_parameter(item)

def _add_conditions_to_template(t, conditions):
    if not conditions:
        return
    for k in conditions:
        t.add_condition(k, conditions[k])


def cf_template(version='2010-09-09', description='', resources=None, outputs=None, parameters=None, conditions=None):
    t = Template()
    t.set_version("2010-09-09")
    t.set_description(description)
    _add_resources_to_template(t, resources)
    _add_outputs_to_template(t, outputs)
    _add_parameters_to_template(t, parameters)
    _add_conditions_to_template(t, conditions)
    return t

def decide_username(imageName):
    imageName = imageName.lower()
    if "cisco" in imageName or 'findit' in imageName:
        return 'cisco'
    if "ubuntu" in imageName:
        return 'ubuntu'
    return 'ec2-user'


class Regions:
    @classmethod
    def get_regions(cls):
        short_codes = cls._get_region_short_codes()

        regions = [{
            'name': cls._get_region_long_name(sc),
            'code': sc
        } for sc in short_codes]

        regions_sorted = sorted(
            regions,
            key=lambda k: k['name']
        )

        return regions_sorted

    @classmethod
    def _get_region_long_name(cls, short_code):
        param_name = (
            '/aws/service/global-infrastructure/regions/'
            f'{short_code}/longName'
        )
        response = ssm.get_parameters(
            Names=[param_name]
        )
        return response['Parameters'][0]['Value']

    @classmethod
    def _get_region_short_codes(cls):
        output = set()
        for page in ssm.get_paginator('get_parameters_by_path').paginate(
            Path='/aws/service/global-infrastructure/regions'
        ):
            output.update(p['Value'] for p in page['Parameters'])

        return output
