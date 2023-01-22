#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common.loggingutils import config_logging
from corgi_common.scriptutils import run_script
from corgi_common.dateutils import YmdHMS
from corgi_common import as_root
import socket
import logging
from icecream import ic

logger = logging.getLogger(__name__)

@click.group(help="Just some script")
def cli():
    pass

@cli.group(help='[command group] openssl utils')
def openssl():
    pass

@cli.command(short_help='Find DHCP Server')
@click.option("--interface", '-i', default='eth0', show_default=True)
def dhcp_discover(interface):
    print(f'nmap -e {interface} --script broadcast-dhcp-discover')

@cli.command(short_help='Shell reflection')
@click.option("--port", '-p', default=48080, type=int, help='Listening port on server', show_default=True)
@click.option("--server", '-s', help='Server hostname/IP', required=True)
def shell_reflect(port, server):
    server_cmd = f'socat TCP-LISTEN:{port},fork,reuseaddr EXEC:"bash -li",pty,stderr,setsid,sigint,sane'
    client_cmd = f'socat file:`tty`,raw,echo=0 tcp:{server}:{port}'
    print("====== Run on server =====")
    print(server_cmd)
    print("====== Run on client =====")
    print(client_cmd)
    pass

@cli.command(short_help='Keep screen awake')
@click.option('--failsafe/--no-failsafe', default=False)
@click.option('--scale', '-s', type=int, default=1)
@click.option('--interval', '-i', type=int, default=120)
def keep_screen_awake(failsafe, scale, interval):
    from itertools import cycle
    import pyautogui
    import time

    print("pyautogui.FAILSAFE:", failsafe)
    print("scale(px):", scale)
    print("interval(s):", interval)
    pyautogui.FAILSAFE = failsafe
    it = cycle([scale, -scale])
    if not hasattr(pyautogui, 'size'):
        print("No mouse in this OS!")
        return
    while True:
        logger.info("moving ...")
        pyautogui.move(next(it), 0)
        time.sleep(interval)
    pass

@cli.command(short_help='Click later')
@click.option('--failsafe/--no-failsafe', default=False)
@click.option('--seconds', '-s', type=int, default=5)
def click_later(failsafe, seconds):
    import pyautogui
    import time

    pyautogui.FAILSAFE = failsafe
    time.sleep(seconds)
    pyautogui.click()
    logger.info("clicked ...")

@cli.command(short_help='Remote forward')
@click.option("--outside-port", '-op', default=48080, type=int, help='Tunnel listening port on outside, effective only in socat mode', show_default=True)
@click.option("--outside-listening-port", '-ol', default=18080, type=int, help='Application listening port on outside', show_default=True)
@click.option("--outside", '-o', help='Outside hostname/IP', required=True)
@click.option("--proxy-ip", '-pi', help='IP proxied by inside', default='localhost', show_default=True)
@click.option("--proxy-port", '-pp', help='Port proxied by inside', required=True)
@click.option("--socat", is_flag=True)
@click.option("--username", '-u', default='<username>', show_default=True)
@click.option("--autogui", is_flag=True)
@click.option("--dry", is_flag=True)
def remote_port_forward(outside, outside_port, outside_listening_port, proxy_ip, proxy_port, socat, username, autogui, dry):
    '''Remote port forward using ssh (prefered) or socat (one-time-use)'''
    if socat:
        # no need to fork, tunnel can be used only once
        outside_cmd = f'socat tcp-l:{outside_port},reuseaddr tcp-l:{outside_listening_port},reuseaddr'
        inside_cmd = f'socat tcp:{outside}:{outside_port},forever,keepalive,keepidle=5,keepcnt=3,keepintvl=5 tcp:{proxy_ip}:{proxy_port}'
        print("====== Run on outside =====")
        print(outside_cmd)
        print("====== Run on inside =====")
        print(inside_cmd)
        return

    cmd = f"ssh -f -N -R {outside_listening_port}:{proxy_ip}:{proxy_port} {username}@{outside}"
    if autogui:
        import pyautogui
        import time

        time.sleep(3)
        pyautogui.write(cmd, interval=0.2)
        if not dry:
            pyautogui.press('enter')
    else:
        print(cmd)

@openssl.command()
@click.option('--port', '-p', default=443, type=int, show_default=True)
@click.argument('site')
def show_site_cert(site, port):
    cmd = f'openssl s_client -showcerts -connect {site}:{port} <<<""'
    _, stdout, _ = run_script(cmd)
    print(stdout)
    pass

@openssl.command()
@click.option('--days', '-d', default=3650, type=int, show_default=True)
@click.option('--common-name', '-cn', 'cn', default='test.com', show_default=True)
@click.option('--organization', '-o', default='CRDC', show_default=True)
@click.option('--san', '-san', required=False, help='subjectAltName ext')
def gen_self_sign_cert(days, cn, organization, san):
    ymdhms = YmdHMS()
    key_filename = f'key-{ymdhms}.pem'
    cert_filename = f'cert-{ymdhms}.pem'
    cmd = f"openssl req -x509 -sha256 -nodes -days {days} -newkey rsa:2048 -keyout {key_filename} -out {cert_filename} -subj /CN={cn}/O={organization}"
    if san:
        san = san.split(',')
        content = ','.join([f'DNS:{s}' for s in san])
        cmd += f' -addext "subjectAltName = {content}"'
    print(cmd)
    run_script(cmd)
    print('done')
    print(f'key: {key_filename}')
    print(f'cert: {cert_filename}')
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

@cli.command(help='restful server')
@click.option("--port", '-p', type=int, default=8081)
def restful(port):
    from flask import request, jsonify, Flask

    ALL_METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH']
    api = Flask(__name__)

    @api.route('/', defaults={'path': ''}, methods=ALL_METHODS)
    @api.route('/<path:path>', methods=ALL_METHODS)
    def _catch_all(path):
        ic(
            path,
            request.method,
            request.url,
            request.base_url,
            request.url_charset,
            request.url_root,
            str(request.url_rule),
            request.host_url,
            request.host,
            request.script_root,
            request.path,
            request.full_path,
            request.args
        )
        return jsonify({'success': True})

    api.run(port=port)

@cli.command(short_help='restful proxy server')
@click.option("--port", '-p', type=int, default=8081)
@click.option("--upstream", '-u', required=True, help='real host, like www.baidu.com')
@click.option("--secure", is_flag=True)
@click.option("--prod", is_flag=True)
def restful_proxy(port, upstream, secure, prod):
    """restful proxy server, take https://www.google.com for example:

    \b
    User[/etc/hosts: 1.2.3.4 www.google.com] (need to install nginx cert, e.g keytool import)

    NGINX(ip/1.2.3.4) [0.0.0.0:443 <-> corgi(localhost:8081)]

    corgi[localhost:8081 <-> www.google.com:443]
    """
    from flask import request, Flask, Response
    import requests
    ALL_METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH']
    EXCLUDED_HEADERS = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    api = Flask(__name__)
    scheme = 'https' if secure else 'http'
    proxy_url = f'{scheme}://{upstream}/'

    def _download_file(streamable):
        with streamable as stream:
            stream.raise_for_status()
            for chunk in stream.iter_content(chunk_size=8192):
                yield chunk

    def _proxy(*args, **kwargs):
        resp = requests.request(
            method=request.method,
            url=request.url.replace(request.host_url, proxy_url),
            headers={key: value for (key, value) in request.headers if key != 'Host'},  # maybe need to add  Host here if upstream is an IP
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            stream=True
        )
        headers = [(name, value) for (name, value) in resp.raw.headers.items() if name.lower() not in EXCLUDED_HEADERS]
        return Response(_download_file(resp), resp.status_code, headers)

    @api.route('/', defaults={'path': ''}, methods=ALL_METHODS)
    @api.route('/<path:path>', methods=ALL_METHODS)
    def _catch_all(path):
        ic(
            path,
            request.method,
            request.url,
            request.base_url,
            request.url_charset,
            request.url_root,
            str(request.url_rule),
            request.host_url,
            request.host,
            request.script_root,
            request.path,
            request.full_path,
            request.args
        )
        return _proxy()

    if prod:
        from waitress import serve
        serve(api, port=port)
    else:
        api.run(port=port, debug=logger.isEnabledFor(logging.DEBUG))


def main():
    config_logging('corgi_misc')
    cli()
