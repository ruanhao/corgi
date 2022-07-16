#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common.loggingutils import config_logging
from corgi_common.scriptutils import run_script
from corgi_common import as_root
import socket
import logging

logger = logging.getLogger(__name__)

@click.group(help="Just some script")
def cli():
    pass


@cli.command(help='Monitor conntrack SNAT events')
def conntrack_monitor_snat():
    # iptables -t nat -A POSTROUTING -s 10.74.107.0/24 ! -d 10.0.0/8 -o eth0 -m state --state NEW -j MASQUERADE
    @as_root
    def _conntrack_monitor_snat():
        run_script("conntrack -E -n", realtime=True)

    _conntrack_monitor_snat()


@cli.command(help='Test netty decoder')
@click.option("--version", type=click.Choice(['v1', 'v2', 'v3', 'v4', 'v5']), default='v1')
@click.option("--host", default='localhost')
@click.option("--port", type=int, default=8080)
def send_length_field_based_frame(version, host, port):
    banner = [
        " _          _ _       \n",
        "| |        | | |      \n",
        "| |__   ___| | | ___  \n",
        "| '_ \ / _ \ | |/ _ \ \n",
        "| | | |  __/ | | (_) |\n",
        "|_| |_|\___|_|_|\___/ \n",
    ]
    logger.info(f"send_length_field_based_frame ({version})")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    if version == 'v1':
        for idx, line in enumerate(banner):
            my_bytes = bytearray()
            length = len(line)
            logger.info(f"sending line {idx}")
            my_bytes.extend(length.to_bytes(2, byteorder='big'))
            my_bytes.extend(line.encode('utf-8'))
            sock.send(my_bytes)
    elif version == 'v2':
        for idx, line in enumerate(banner):
            my_bytes = bytearray()
            length = len(line)
            logger.info(f"sending line {idx}")
            my_bytes.extend(b'\xCA\xFE')  # magic
            my_bytes.extend(length.to_bytes(2, byteorder='big'))
            my_bytes.extend(line.encode('utf-8'))
            sock.send(my_bytes)
    elif version == 'v3':
        for idx, line in enumerate(banner):
            my_bytes = bytearray()
            length = len(line)
            logger.info(f"sending line {idx}")
            my_bytes.extend(length.to_bytes(3, byteorder='big'))
            my_bytes.extend(b'\xCA\xFE')  # magic
            my_bytes.extend(line.encode('utf-8'))
            sock.send(my_bytes)
    elif version == 'v4':
        for idx, line in enumerate(banner):
            my_bytes = bytearray()
            length = len(line)
            logger.info(f"sending line {idx}")
            my_bytes.extend(b'\xCA')  # magic
            my_bytes.extend(length.to_bytes(2, byteorder='big'))
            my_bytes.extend(b'\xFE')  # magic
            my_bytes.extend(line.encode('utf-8'))
            sock.send(my_bytes)
    elif version == 'v5':
        for idx, line in enumerate(banner):
            my_bytes = bytearray()
            length = len(line) + 4  # 4: 1 for \xCA, 1 for \xFE, 2 for length itself
            logger.info(f"sending line {idx}")
            my_bytes.extend(b'\xCA')  # magic
            my_bytes.extend(length.to_bytes(2, byteorder='big'))
            my_bytes.extend(b'\xFE')  # magic
            my_bytes.extend(line.encode('utf-8'))
            sock.send(my_bytes)
    pass


def main():
    config_logging('corgi_misc')
    cli()
