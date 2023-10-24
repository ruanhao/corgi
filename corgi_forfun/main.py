#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import json
from click import echo
import os
from corgi_common import config_logging
import logging
from icecream import ic
import uuid
from corgi_common.restutils import *
from corgi_rabbit.main import _rabbit_channel

logger = logging.getLogger(__name__)

FORFUN_HOST = os.getenv('FORFUN_HOST', 'localhost')
FORFUN_PORT = os.getenv('FORFUN_PORT', 5802)  # 5802 is my CCIE number
FORFUN_BASE_URL = f'http://{FORFUN_HOST}:{FORFUN_PORT}/api'

def _forfun_url(uri):
    return FORFUN_BASE_URL + uri

def _redis_url(uri):
    url = _forfun_url('/redis') + uri
    return ic(url)

def _rabbit_url(uri):
    url = _forfun_url('/rabbit') + uri
    return ic(url)

@click.group(help="for fun test", context_settings=dict(help_option_names=['-h', '--help']))
def cli():
    pass

@cli.group(help='Redis for fun [command group]')
def redis():
    pass

@cli.group(help='Rabbit for fun [command group]')
def rabbit():
    pass

@redis.command(name='set')
@click.argument('key', required=True)
@click.argument('value', required=True)
def do_set(key, value):
    http_put(
        _redis_url('/set'),
        json={
            'key': ic(key),
            'value': value
        }
    )

@redis.command(name='pub')
@click.argument('channel', required=True)
@click.argument('data', required=True)
def do_pub(channel, data):
    http_post(
        _redis_url('/pub'),
        json={
            'channel': ic(channel),
            'data': data
        }
    )

@redis.command(name='get')
@click.argument('key', required=True)
def do_get(key):
    response_data = http_get(
        _redis_url('/get/' + key),
    ).json()
    echo(response_data.get('value'))

def main():
    config_logging('corgi_forfun')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass


@rabbit.command(name='pub')
@click.argument('rk', default='forfun.test')
def rabbit_pub(rk):
    http_post(
        _rabbit_url("/pub/" + rk),
        json={
            'id': str(uuid.uuid4()),
            'name': "test"
        }
    )
    pass

@rabbit.command(name='unbind')
def rabbit_unbind():
    """after binding is removed, there is will be no react to publish"""
    http_delete(_rabbit_url("/unbind"))

@rabbit.command(name='bind')
def rabbit_bind():
    """bind dynamically"""
    http_post(_rabbit_url("/bind"))


@rabbit.command(short_help='test alternate ex', name='ae')
def rabbit_ae():
    """can see message is routed to blackhole"""
    channel = _rabbit_channel(FORFUN_HOST, 5672, '/', 'guest', 'guest')
    channel.basic_publish(
        exchange='x_walle',
        routing_key='whatever',
        body=json.dumps(
            {
                'id': str(uuid.uuid4())
            }
        ),
    )
