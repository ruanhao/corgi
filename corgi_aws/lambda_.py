import click
import logging
import os
from corgi_common import bye, switch_to_tmp_dir, run_script, goodbye
from troposphere import Ref
from corgi_common.dateutils import YmdHMS
from os.path import abspath
from troposphere.serverless import (
    Function, SERVERLESS_TRANSFORM, CloudWatchEvent,
    EventInvokeConfiguration, OnSuccess, OnFailure, DestinationConfiguration
)
from troposphere.sns import Topic
from .common import cf_template
from awacs.aws import Policy, Statement, Action

client = None


logger = logging.getLogger(__name__)


def fatal(msg):
    logger.critical(msg)
    bye(msg)


def info(msg):
    logger.info(msg)
    click.echo(msg)


@click.group(help="Utils for Serverless")
def lambda_():
    pass


@lambda_.command(help="Create event-driven Python Function")
@click.option("--name", '-n', required=True, help='Lambda/Stack name prefix')
@click.option("--lambda-function-file", '-f', required=True, type=click.Path(exists=True))
@click.option("--requirements-file", type=click.Path(exists=True), help='requirements.txt')
@click.option("--dependencies", '-d', help='Module Dependencies')
@click.option("--description", default='Created by corgi')
@click.option("--event-sources", default='aws.ec2')
@click.option("--s3-bucket", required=True, help='S3 bucket name (no s3://)')
@click.option("--dry", is_flag=True)
def create_function(name, lambda_function_file, requirements_file, dependencies, dry, description, event_sources, s3_bucket):
    ymdhms = YmdHMS()
    stack_name = name + "Stack" + ymdhms
    function_name = 'Function'
    requirements_file = requirements_file and abspath(requirements_file)
    lambda_function_file = abspath(lambda_function_file)

    with open(lambda_function_file, 'r') as f:
        text = f.read()
        if len(text) < len("def lambda_handler():") or 'lambda_handler' not in text:
            bye("Malformat Lambda function file")

    resources = [
        Topic(
            "OnSuccess",
        ),
        Topic(
            "OnFailure",
        ),
        Function(
            function_name,
            CodeUri=".",
            Runtime='python3.8',
            Handler='lambda_function.lambda_handler',
            Policies=[
                Policy(
                    Statement=[
                        Statement(
                            Effect='Allow',
                            Action=[Action('ec2', '*')],   # just for simplicity, please modify it in real world (check corgi_aws policy list-actions <service-name>)
                            Resource=['*']  # just for simplicity, please modify it in real world
                        )
                    ],
                    Version='2012-10-17'
                ),
            ],
            Events={
                "CloudTrail": CloudWatchEvent(
                    "WhyNeedToSpecifyANameHere",
                    Pattern={
                        'detail-type': ['AWS API Call via CloudTrail'],  # this is the most common event type
                        'source': event_sources.split(','),
                        # 'detail': {'eventName': ['RunInstance']}
                    }
                )
            },
            EventInvokeConfig=EventInvokeConfiguration(
                DestinationConfig=DestinationConfiguration(
                    OnSuccess=OnSuccess(Destination=Ref('OnSuccess'), Type='SNS'),
                    # OnFailure=OnFailure(Destination=Ref('OnFailure'), Type='SNS'),
                )
            ),
        ),
    ]
    t = cf_template(description=description, resources=resources)
    t.set_transform(SERVERLESS_TRANSFORM)
    if dry:
        print(t.to_yaml())
        goodbye()
    with switch_to_tmp_dir():
        info(f"=> {os.getcwd()}")
        if dependencies:
            for dep in dependencies.split(','):
                run_script(f"pip install {dep} --target .", realtime=True)
        elif requirements_file:
            run_script(f'pip install -r {requirements_file} --target .', realtime=True)
        with open(lambda_function_file, 'rb') as f0:
            with open('lambda_function.py', 'wb') as f1:
                f1.write(f0.read())
        with open('template0.yaml', 'w') as f:
            f.write(t.to_yaml())

        info("Preparing S3 code uri ...")
        # after this, CodeUri will be set automatically
        run_script('aws cloudformation package --template-file template0.yaml '
                   f'--s3-bucket {s3_bucket} --output-template-file template.yaml', dry=dry, realtime=True)

        info(f"Deploying stack ({stack_name}) ...")
        # `aws cloudformation deploy` will firstly create stack and then apply change set for AWS::Serverless transform
        run_script(f'aws cloudformation deploy --stack-name {stack_name} '
                   '--template-file template.yaml --capabilities CAPABILITY_IAM --tags=creator=haoru', realtime=True, dry=dry)
