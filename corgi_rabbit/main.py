#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import json
from corgi_common import config_logging, pretty_print, get, bye
from corgi_common.dateutils import pretty_duration, now
import logging
import pika
import sys
import requests
# from urllib3.parse import

logger = logging.getLogger(__name__)

EXCHANGES_URL = '/api/exchanges'
QUEUES_URL = '/api/queues'
BINDINGS_URL = '/api/bindings'
OVERVIEW_URL = '/api/overview'
NODES_URL = '/api/nodes'

def _uri(host, port, uri):
    return f"http://{host}:{port}" + uri

def _rabbit_get(uri, host, port, username, password):
    r = requests.get(_uri(host, port, uri), auth=(username, password))
    return r.json()


def info(msg):
    print(msg, flush=True)
    # sys.stdout.flush()
    logger.info(msg)

def _color(v, func):
    if func(v):
        return click.style(str(v), fg='red')
    else:
        return str(v)


@click.group(help="CLI tool for RabbitMQ")
def cli():
    pass

@cli.command(help='List bindings')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--queue', '-q', help='Queue name')
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--port', '-p', default=15672, type=int, show_default=True, help='HTTP Management port')
@click.option('--vhost', default='/', type=str, show_default=True)
@click.option('-x', is_flag=True)
@click.option('--json', 'json_format', is_flag=True)
def ls_bindings(host, port, username, password, vhost, x, json_format, queue):
    if queue:
        uri = QUEUES_URL + "/" + requests.utils.quote(vhost, safe='') + f"/{queue}/bindings"
    else:
        uri = BINDINGS_URL + "/" + requests.utils.quote(vhost, safe='')
    pretty_print(_rabbit_get(uri, host, port, username, password), mappings={
        'exchange': ('source', lambda e: '[Default Direct Ex]' if not e else e),
        'destination': 'destination',
        # 'destination_type': 'destination_type',
        'routing_key': 'routing_key',
        'args': 'arguments',
    }, x=x, json_format=json_format)
    pass

@cli.command(help='List queues')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--port', '-p', default=15672, type=int, show_default=True, help='HTTP Management port')
@click.option('--vhost', default='/', type=str, show_default=True)
@click.option('-x', is_flag=True)
@click.option('--json', 'json_format', is_flag=True)
def ls_queues(host, port, username, password, vhost, x, json_format):
    uri = QUEUES_URL + "/" + requests.utils.quote(vhost, safe='')
    pretty_print(_rabbit_get(uri, host, port, username, password), mappings={
        'name': 'name',
        # 'type': 'type',
        'auto_delete': 'auto_delete',
        'durable': 'durable',
        'exclusive': 'exclusive',
        'consumers': 'consumers',
        'messages': 'messages',
        'unacknowledged': 'messages_unacknowledged',
    }, x=x, json_format=json_format)
    pass

@cli.command(help='List exchanges')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--port', '-p', default=15672, type=int, show_default=True, help='HTTP Management port')
@click.option('--vhost', default='/', type=str, show_default=True)
@click.option('-x', is_flag=True)
@click.option('--json', 'json_format', is_flag=True)
def ls_exchanges(host, port, username, password, vhost, x, json_format):
    uri = EXCHANGES_URL + "/" + requests.utils.quote(vhost, safe='')
    pretty_print(_rabbit_get(uri, host, port, username, password), mappings={
        'name': 'name',
        'type': 'type',
        'auto_delete': 'auto_delete',
        'durable': 'durable',
        'pre-defined': ('user_who_performed_action', lambda v: "True" if v == 'rmq-internal' else ''),
        'in': ('message_stats', _exchange_in_stat),
        'out': ('message_stats', _exchange_out_stat),
    }, x=x, json_format=json_format)
    # pprint(_rabbit_get(uri, host, port, username, password))
    pass

def _rabbit_channel(host, port, vhost, username, password):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            heartbeat=600,
            credentials=pika.PlainCredentials(username=username, password=password),
            host=host,
            port=port,
            virtual_host=vhost,
        ))
    except Exception as error:
        bye(f"Cannot open connection to {host}:{port} [{error}]")
    if not connection.is_open:
        bye(f"Cannot open connection to {host}:{port}")
    return connection.channel()


@cli.command(help='Overview')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--port', '-p', default=15672, type=int, show_default=True, help='RabbitMQ HTTP Management port')
@click.option('--json', 'json_format', is_flag=True)
def overview(host, port, username, password, json_format):
    resp = _rabbit_get(OVERVIEW_URL, host, port, username, password)
    x = False if json_format else True
    pretty_print([resp], mappings={
        'version': ('', lambda obj: f"{obj['rabbitmq_version']} (Erlang:{obj['erlang_version']})"),
        'cluster': 'cluster_name',
        'connections': 'object_totals.connections',
        'channels': 'object_totals.channels',
        'exchanges': 'object_totals.exchanges',
        'queues': 'object_totals.queues',
        'consumers': 'object_totals.consumers',
        'ports': ('listeners', _port_info),
    }, x=x, json_format=json_format, header=False)
    pass

def _port_info(listeners):
    return ','.join([f"{listener['port']}/{listener['protocol']}" for listener in listeners])


@cli.command(help='Nodes info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--port', '-p', default=15672, type=int, show_default=True, help='RabbitMQ HTTP Management port')
@click.option('--json', 'json_format', is_flag=True)
@click.option('-x', is_flag=True)
def ls_nodes(host, port, username, password, json_format, x):
    resp = _rabbit_get(NODES_URL, host, port, username, password)
    pretty_print(resp, mappings={
        'name': 'name',
        'uptime': ('uptime', lambda up: pretty_duration(up / 1000)),
        'ticktime': 'net_ticktime',
        'mem_used (mb)': ('mem_used', lambda b: int(b / 1024 / 1024)),
        'procs': 'proc_used',
    }, x=x, json_format=json_format)
    pass


@cli.command(help='Eavesdrop messages for exchange')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--port', '-p', default=5672, type=int, show_default=True, help='RabbitMQ port')
@click.option('--vhost', default='/', type=str, show_default=True)
@click.option('--exchange', '-e', required=True, type=str)
@click.option('--route-key', '-rk', default='#', type=str, show_default=True)
def tap(host, port, username, password, vhost, exchange, route_key):
    channel = _rabbit_channel(host, port, vhost, username, password)
    queue = channel.queue_declare('', durable=False, exclusive=True, auto_delete=True).method.queue
    logger.info(f"Created queue {queue}")
    channel.queue_bind(queue, exchange, route_key)
    logger.info(f"Queue {queue} bound to exchange {exchange} with routing key: {route_key}")
    count = 1

    def _handle_msg(msg0):
        nonlocal count
        logger.info(f'[RECORD {count}]: {msg0}')
        try:
            msg = json.dumps(json.loads(msg0), indent=2, default=str, sort_keys=True)
            # msg = json.dumps(msg0, indent=2, default=str, sort_keys=True)
        except Exception as e:
            logger.error(f"Failed to dump json content: {e}")
            msg = msg0
            pass
        header = f'-[ RECORD {count} {now()} ]-'.ljust(100, '-')
        output = f'{header}\n{msg}'
        print(output, flush=True)
        sys.stdout.flush()
        count += 1

    def _cb(c, m, p, b):
        msg = b.decode("utf-8")
        _handle_msg(msg)
        dt = m.delivery_tag
        c.basic_ack(dt)

    channel.basic_consume(queue, _cb)
    channel.start_consuming()
    pass

def _exchange_in_stat(stat):
    if not isinstance(stat, dict):
        return ''
    count = get(stat, 'publish_in', 0)
    rate = get(stat, 'publish_in_details.rate', 0.0)
    return f"{count}/{rate}"

def _exchange_out_stat(stat):
    if not isinstance(stat, dict):
        return ''
    count = get(stat, 'publish_out', 0)
    rate = get(stat, 'publish_out_details.rate', 0.0)
    return f"{count}/{rate}"

def main():
    config_logging('corgi_rabbit')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
