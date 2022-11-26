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
from icecream import ic
# from urllib3.parse import

logger = logging.getLogger(__name__)

EXCHANGES_URL = '/api/exchanges'
QUEUES_URL = '/api/queues'
BINDINGS_URL = '/api/bindings'
OVERVIEW_URL = '/api/overview'
NODES_URL = '/api/nodes'

def _uri(host, port, uri):
    url = f"http://{host}:{port}" + uri
    return ic(url)

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
        'x': ('source', lambda e: '[Default Direct X]' if not e else e),  # exchange
        'rk': 'routing_key',
        'dst': 'destination',  # ex or queue
        'dst type': 'destination_type',
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
        # 自动删除的前提是: *之前*至少有一个消费者连接到这个队列，*之后*所有与这个队列连接的消费者都断开时，才会自动删除
        'auto_delete': 'auto_delete',
        'durable': 'durable',
        # 如果一个队列被声明为排他队列，该队列仅对首次声明它的连接可见，并在连接断开时自动删除。
        # 这里需要注意三点: 排他队列是基于连接(Connection)可见的，同一个连接的不同信道(Channel)是可以同时访问同一连接创建的排他队列;
        # *首次*是指如果一个连接己经声明了一个排他队列，其他连接是不允许建立同名的排他队列的，
        # 这个与普通队列不同:即使该队列是持久化的，一旦连接关闭或者客户端退出，该排他队列都会被自动删除，
        # 这种队列适用于一个客户端同时发送和读取消息的应用场景
        'exclusive': 'exclusive',
        'args': 'arguments',
        'consumers': 'consumers',
        'ready': 'messages_ready',  # 等待投递给消费者的消息数
        'unacked': 'messages_unacknowledged',  # 己经投递给消费者但是未收到确认信号的消息数
        'total': 'messages',    # Ready+Unacked
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
        # 自动删除的前提是*之前*至少有一个队列或者交换器与这个交换器绑定，*之后*所有与这个交换器绑定的队列或者交换器都与此解绑
        'auto_delete': 'auto_delete',
        'durable': 'durable',
        'args': 'arguments',
        'pre-defined': ('user_who_performed_action', lambda v: "y" if v == 'rmq-internal' else ''),
        'in': ('message_stats', _exchange_in_stat),
        'out': ('message_stats', _exchange_out_stat),
    }, x=x, json_format=json_format)
    # pprint(_rabbit_get(uri, host, port, username, password))
    pass

def is_json(myjson):
    try:
        json.loads(myjson)
    except ValueError:
        return False
    return True

@cli.command(help='Basic publish')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--username', '-u', default='guest', show_default=True)
@click.option('--password', '-P', default='guest', show_default=True)
@click.option('--vhost', default='/', type=str, show_default=True)
@click.option('--port', '-p', default=5672, type=int, show_default=True, help='RabbitMQ port')
@click.option('--exchange', '-e', default='', type=str)
@click.option('--route-key', '-rk', required=True)
@click.option('--mandatory', '-m', is_flag=True)
@click.option('--transient', is_flag=True)
@click.argument('message')
def pub(host, username, password, port, vhost, exchange, route_key, message, mandatory, transient):
    channel = _rabbit_channel(host, port, vhost, username, password)
    content_type = 'application/json' if is_json(message) else 'text/plain'
    delivery_mode = pika.DeliveryMode.Transient if transient else pika.DeliveryMode.Persistent
    try:
        channel.basic_publish(
            exchange=ic(exchange),
            routing_key=ic(route_key),
            body=message,
            # 当 mandatory 参数设为 true ，若交换器无法根据自身的类型和路由键找到一个符合条件的队列，RabbitMQ 会调用 Basic.Return 命令将消息返回给生产者
            # 如果备份交换器和 mandatory 参数一起使用，那么 mandatory 参数无效
            mandatory=ic(mandatory),
            properties=pika.BasicProperties(
                content_type=ic(content_type),
                delivery_mode=ic(delivery_mode),
            ),
        )
    except pika.exceptions.UnroutableError as e:
        click.echo(e, err=True)
        for idx, message in enumerate(e.messages, 1):
            click.echo(f"{idx}:", err=True)
            click.echo(message.body, err=True)
        exit(1)
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
    channel = connection.channel()
    channel.confirm_delivery()
    return ic(channel)


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
@click.option('--prefetch-count', '-pc', default=1, type=int, show_default=True)
def tap(host, port, username, password, vhost, exchange, route_key, prefetch_count):
    channel = _rabbit_channel(host, port, vhost, username, password)
    queue = channel.queue_declare('', durable=False, exclusive=True, auto_delete=True).method.queue
    logger.info(f"Created queue {queue}")
    channel.queue_bind(queue, exchange, route_key)
    logger.info(f"Queue {queue} bound to exchange {exchange} with routing key: {route_key}")
    count = 1

    def _handle_msg(rk, msg0):
        nonlocal count
        logger.info(f'[RECORD {count} (#{rk})]: {msg0}')
        try:
            msg = json.dumps(json.loads(msg0), indent=2, default=str, sort_keys=True)
            # msg = json.dumps(msg0, indent=2, default=str, sort_keys=True)
        except Exception as e:
            logger.error(f"Failed to dump json content: {e}")
            msg = msg0
            pass
        header = f'-[ RECORD {count} #{rk} {now()} ]-'.ljust(100, '-')
        output = f'{header}\n{msg}'
        print(output, flush=True)
        sys.stdout.flush()
        count += 1

    def _cb(c, m, p, b):
        logger.debug(f"c:{c}, m:{m}, p:{p}, b:{b}")
        msg = b.decode("utf-8")
        rk = m.routing_key
        _handle_msg(rk, msg)
        dt = m.delivery_tag
        c.basic_ack(dt)

    channel.basic_qos(prefetch_count=ic(prefetch_count))
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
