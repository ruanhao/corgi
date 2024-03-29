import click
import logging
import boto3
from qqutils import hprint
client = None

logger = logging.getLogger(__name__)


def fatal(msg):
    logger.critical(msg)
    click.echo(msg, err=True)
    raise click.Abort()

def _get_zone_ids():
    zones = client.list_hosted_zones()['HostedZones']
    return [zone['Id'] for zone in zones]

def _get_zone_id(zone_name):
    zones = client.list_hosted_zones()['HostedZones']
    for zone in zones:
        if zone_name in zone['Name']: return zone['Id']
    fatal(f"Zone ({zone_name}) not found")


def info(msg):
    logger.info(msg)
    click.echo(msg)


@click.group(help="Utils for Route53")
@click.option('--api-key', '-h', envvar='AWS_ACCESS_KEY_ID_FOR_API', required=True, help='This is a workaroud, have to use another key/secret, oops')
@click.option('--api-secret', '-u', envvar='AWS_SECRET_ACCESS_KEY_FOR_API', required=True, help='This is a workaroud')
def route53(api_key, api_secret):
    session = boto3.Session(
        aws_access_key_id=api_key,
        aws_secret_access_key=api_secret,
    )
    global client
    client = session.client('route53')


@route53.command(help="List record")
@click.option("--zone", "-z", help="Zone name", required=False)
def ls_record(zone):
    if zone:
        zone_ids =  [_get_zone_id(zone)]
    else:
        zone_ids = _get_zone_ids()

    for zone_id in zone_ids:
        response = client.list_resource_record_sets(HostedZoneId=zone_id)
        record_sets = response['ResourceRecordSets']
        result = []
        for record in record_sets:
            if record['Type'] == 'A':
                result.append({'name': record['Name'], 'value': record['ResourceRecords'][0]['Value'], 'type': record['Type']})
        if result:
            hprint(result, mappings={
                'IP': 'value',
                'Name': 'name',
                # 'Type': 'type',
            })
            print()

    pass


@click.command(help="Create record")
@click.option("--name", "-n", help="Record name", required=True)
@click.option("--zone", "-z", help="Zone name", default='finditnm.com')
@click.option("--ip", "-i", help="IP Address", required=True)
def create_record(name, zone, ip):
    info(f"Upserting record ({name}.{zone} => {ip}) ...")
    response = client.change_resource_record_sets(
        ChangeBatch={
            'Changes': [
                {
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': f"{name}.{zone}",
                        'ResourceRecords': [
                            {
                                'Value': ip,
                            },
                        ],
                        'TTL': 300,
                        'Type': 'A',
                    },
                },
            ],
            'Comment': 'created by haoru',
        },
        HostedZoneId=_get_zone_id(zone),
    )
    change_id = response['ChangeInfo']['Id']
    waiter = client.get_waiter('resource_record_sets_changed')
    click.echo("Waiting for completion ...")
    waiter.wait(
        Id=change_id,
        WaiterConfig={
            'Delay': 3,
            'MaxAttempts': 30
        }
    )
    pass


route53.add_command(create_record)
