#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import time
import socket
import logging
from icecream import ic
import codecs
from qqutils import run_proxy, as_root, run_script, YmdHMS, configure_logging, from_cwd, is_port_in_use, submit_thread, hprint, prompt, add_suffix
from tempfile import NamedTemporaryFile
import os

logger = logging.getLogger(__name__)


@click.group(help="Just some script", context_settings=dict(help_option_names=['-h', '--help']))
@click.pass_context
@click.option("--debug", "-v", "verbose", is_flag=True)
def cli(ctx, verbose):
    configure_logging('corgi_misc', level=logging.DEBUG if verbose else logging.INFO, setup_ic=True)
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
@click.option('--port', '-p', default=443, type=int, show_default=True)
@click.argument('host', required=True)
def show_site_ciphers(host, port):
    cmd = f'nmap --script ssl-enum-ciphers -p {port} {host}'
    _, stdout, _ = run_script(cmd)
    print(stdout)


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


@cli.command(help='TCP port forwarder')
@click.pass_context
@click.option('--local-server', '-l', default='localhost', help='Local server')
@click.option('--local-port', '-lp', type=int, default=8080, help='Local port')
@click.option('--remote-server', '-r', default='localhost', help='Remote server')
@click.option('--remote-port', '-rp', type=int, default=8000, help='Remote port')
@click.option('--global', '-g', 'using_global', is_flag=True, help='Listen on 0.0.0.0')
@click.option('--content', '-c', is_flag=True, help='Show content')
@click.option('--to-file', '-f', is_flag=True, help='Save content to file')
@click.option('--tls', '-s', is_flag=True, help='Denote TLS connection')
@click.option('-ss', is_flag=True, help='Denote TLS connection for proxy server')
def tcp_port_forward(ctx, local_server, local_port, remote_server, remote_port, using_global, content, to_file, tls, ss):
    if using_global:
        local_server = '0.0.0.0'

    if content:
        codecs.register_error('using_dot', lambda e: ('.', e.start + 1))

    def _handle(buffer, direction, src, dst):
        nonlocal to_file
        src_ip, src_port = src.getpeername()
        dst_ip, dst_port = dst.getpeername()
        content = buffer.decode('ascii', errors='using_dot')

        filename = ('L' if direction else 'R') + f'_{src_ip}_{src_port}_{dst_ip}_{dst_port}.log'
        if to_file:
            with from_cwd('__tcpflow__', filename).open('a') as f:
                f.write(content)
        click.secho(content, fg='green' if direction else 'yellow')
        return buffer

    run_proxy(local_server, local_port, remote_server, remote_port, handle=_handle if content else None, tls=tls, tls_server=ss)

@cli.group(help='[command group] letsencrypt utils')
def letsencrypt():
    pass

def _run_challenge_server(webroot):
    import flask
    from flask import request

    ALL_METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH']
    api = flask.Flask(__name__)

    def _show_request():
        path = request.full_path if request.args else request.path
        remote_port = request.environ.get('REMOTE_PORT')
        remote = f"{request.remote_addr}:{remote_port}"
        prefix = f"[{remote}] "
        request_body = f"""{request.method} {path} {request.environ['SERVER_PROTOCOL']}
{request.headers}"""
        data = request.get_data(as_text=True)[:100]
        if data:
            request_body += data
        print(os.linesep.join([prefix + line for line in request_body.splitlines()]))
        print()

    @api.route('/.well-known/acme-challenge/<filename>', methods=['GET'])
    def acme_challenge(filename):
        # _show_request()
        fn = os.path.join(webroot, ".well-known", 'acme-challenge', filename)
        print(f"being challenged [{fn}]...")
        with open(fn) as f:
            return f.read(), 200

    @api.route('/', defaults={'path': ''}, methods=ALL_METHODS)
    @api.route('/<path:path>', methods=ALL_METHODS)
    def _default(path):
        _show_request()
        return '', 200

    print('Challenge http server started listening 80')

    api.run(host='0.0.0.0', port=80)


@letsencrypt.command(help='renew letsencrypt cert')
@click.pass_context
def renew(ctx, domains, email):
    run_script('sudo certbot renew --force-renewal --no-random-sleep-on-renew', real_time=True)

@letsencrypt.command(help='generate letsencrypt cert')
@click.option('--domains', '-d', required=True, help='domain names')
@click.option('--email', '-e', help='email')
@click.pass_context
def cert_only(ctx, domains, email):
    assert not is_port_in_use(80), 'Port 80 is in use, please stop the process and try again'

    webroot = from_cwd('__tmp__')
    if not webroot.exists():
        webroot.mkdir()
        os.chmod(webroot, 0o777)

    submit_thread(_run_challenge_server, webroot)

    deploy_hook_script_file = NamedTemporaryFile(delete=False)
    print("deploy_hook_script_file:", deploy_hook_script_file.name)
    with open(deploy_hook_script_file.name, 'w') as f:
        f.write("""#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# Description:

_SCRIPT_NAME=$(basename $0)
_SCRIPT_DIR=$(dirname $(realpath $(which $0)))

log_info() {
    echo "$(date +'%Y-%m-%dT%H:%M:%S.%3N%z') [$$] INFO ${_SCRIPT_NAME} $@" >> /tmp/corgi_letsencrypt.log
}

log_info "On cert renewal for [$RENEWED_DOMAINS]"

log_info "Cleaning up tmp file ..."
tmp_fullchain_pem_file=/tmp/fullchain.pem
rm -rf $tmp_fullchain_pem_file || true

log_info "Creating fullchain pem file ..."
cat $RENEWED_LINEAGE/fullchain.pem > $tmp_fullchain_pem_file
curl -s https://letsencrypt.org/certs/isrgrootx1.pem >> $tmp_fullchain_pem_file
""" + f"""
log_info "Copying key and cert to {webroot} ..."
cp $RENEWED_LINEAGE/privkey.pem {webroot}/key.pem
cp $tmp_fullchain_pem_file {webroot}/cert.pem
""")
    os.chmod(deploy_hook_script_file.name, 0o777)
    deploy_hook_script_file.file.close()

    command = f'sudo certbot certonly --non-interactive --agree-tos --no-eff-email --webroot -w {webroot} -d {domains}'

    if email:
        command += f' -m {email}'
    else:
        command += ' --register-unsafely-without-email'

    command += f' --deploy-hook {deploy_hook_script_file.name}'
    command += ' --force-renewal --expand'
    print(command)
    logger.info(command)
    run_script(command, realtime=True, logger=logger)
    while True:
        if os.path.exists(webroot / 'cert.pem') and os.path.exists(webroot / 'key.pem'):
            print("done")
            break
        time.sleep(1)
    exit(0)


@cli.group(help='[command group] youtube downloader utils')
def youtube():
    """https://pytube.io/en/latest/index.html"""
    pass

@youtube.command(help='show youtube video caption')
@click.option('--url', '-u', required=True, help='youtube video url')
@click.option('--sock5-proxy-ip', help='sock5 proxy ip')
@click.option('--sock5-proxy-port', help='sock5 proxy port')
@click.pass_context
def caption(ctx, url, sock5_proxy_ip, sock5_proxy_port):
    from pytube import YouTube
    proxies = None
    if sock5_proxy_ip and sock5_proxy_port:
        proxies = {
            'http': f"socks5://{sock5_proxy_ip}:{sock5_proxy_port}",
            'https': f"socks5://{sock5_proxy_ip}:{sock5_proxy_port}"
        }

    youtube = YouTube(url, proxies=proxies)
    captions = youtube.captions
    print(captions)


@youtube.command(help='download youtube video')
@click.option('--url', '-u', required=True, help='youtube video url')
@click.option('--sock5-proxy-ip', help='sock5 proxy ip')
@click.option('--sock5-proxy-port', help='sock5 proxy port')
@click.option('--time-start', '-s', help="start time, can be expressed in seconds (15.35), in (min, sec), in (hour, min, sec), or as a string: '01:03:05.35'.")
@click.option('--time-end', '-e')
@click.pass_context
def download(ctx, url, sock5_proxy_ip, sock5_proxy_port, time_start, time_end):
    from pytube import YouTube
    proxies = None
    if sock5_proxy_ip and sock5_proxy_port:
        # os.environ['ALL_PROXY'] = f"socks5://{sock5_proxy_ip}:{sock5_proxy_port}"

        # import socks
        # import socket
        # socks.set_default_proxy(socks.PROXY_TYPE_SOCKS5, sock5_proxy_ip, sock5_proxy_port)
        # socket.socket = socks.socksocket
        proxies = {
            'http': f"socks5://{sock5_proxy_ip}:{sock5_proxy_port}",
            'https': f"socks5://{sock5_proxy_ip}:{sock5_proxy_port}"
        }
    fps = 25

    def _on_progress_callback(_chunk, _fh, bytes_remaining):
        print(f"{bytes_remaining} bytes ({round(bytes_remaining / 1024 / 1024)} M) remaining ...")

    def _on_complete_callback(_stream, file_path):
        print(f"download completed: {file_path}")
        nonlocal time_start, time_end, fps
        if not time_start:
            return
        from moviepy.editor import VideoFileClip
        video = VideoFileClip(file_path).subclip(time_start, time_end)
        clip_path = add_suffix(file_path, '-clip')
        video.write_videofile(clip_path, fps=fps)
        print(f"done with clipping, fps: {fps}, file: {clip_path}")

    youtube = YouTube(
        url,
        on_progress_callback=_on_progress_callback,
        on_complete_callback=_on_complete_callback,
        proxies=proxies,
    )
    streams = youtube.streams
    # print(dir(streams[0]))
    hprint(streams, mappings={
        'itag': ('', lambda x: x.itag),
        'mime_type': ('', lambda x: x.mime_type),
        'fps': ('', lambda x: fps),
        # 'progressive': ('', lambda x: x.progressive),
        'type': ('', lambda x: x.type),
        'resolution': ('', lambda x: x.resolution),
        'filesize(MB)': ('', lambda x: x._filesize_mb),
        'audio': ('', lambda x: "y" if x.includes_audio_track else ""),
    })
    highest_resolution_video = (streams.filter(file_extension='mp4')
                                .order_by('resolution')
                                .desc()
                                .first())
    fps = highest_resolution_video.fps
    itag = prompt("Select itag", default=highest_resolution_video.itag)
    print("Start downloading ...")
    streams.get_by_itag(itag).download()


def main():
    cli()
