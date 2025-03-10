#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import time
import socks
import socket
import logging
from icecream import ic
from typing import Optional, Dict
import codecs
from datetime import datetime, timedelta
from qqutils import run_proxy, as_root, run_script, YmdHMS, configure_logging, from_cwd, is_port_in_use, submit_thread, hprint, prompt, add_suffix, pinfo, get_param, modify_extension, perror, switch_dir, red, green, time_measurer
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

@openssl.command()
@click.option('--csr', '-csr', type=click.Path(exists=True), required=False)
@click.option('--key', '-k', type=click.Path(exists=True), required=False)
@click.option('--days', '-d', default=3650, type=int, show_default=True)
@click.option('--common-name', '-cn', 'cn', default='test.com', show_default=True)
@click.option('--organization', '-o', default='CRDC', show_default=True)
@click.option('--san', '-san', required=False, help='subjectAltName ext')
@click.pass_context
def sign_csr(ctx, csr, key, days, cn, organization, san):
    from cryptography.hazmat.primitives import serialization
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa

    if not key:
        # 生成 RSA 私钥
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # 保存私钥
        pem_private_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        with open("private_key.pem", "wb") as f:
            f.write(pem_private_key)
    else:
        with open(key, 'rb') as f:
            pem_private_key = f.read()
            private_key = serialization.load_pem_private_key(pem_private_key, password=None)

    if not csr:
        # 生成 CSR
        builder = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, u"CN"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Shanghai"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, u"Shanghai"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                x509.NameAttribute(NameOID.COMMON_NAME, cn),
            ])
        )
        if san:
            builder.add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(san)
                ]),
                critical=False,
            )

        csr = builder.sign(private_key, hashes.SHA256())
        # 保存 CSR
        pem_csr = csr.public_bytes(serialization.Encoding.PEM)
        with open("csr.pem", "wb") as f:
            f.write(pem_csr)
    else:
        with open(csr, 'rb') as f:
            pem_csr = f.read()
            csr = x509.load_pem_x509_csr(pem_csr)

    # 生成证书
    certificate = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(csr.subject)  # 自签名证书，所以颁发者是自己
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    # 保存证书
    with open("certificate.pem", "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))


# pip install pylint
# pyreverse -f ALL -ASmy -d __output__ -o html -c langchain_community.chat_models.ollama.ChatOllama langchain_community
@cli.command(help='Show UML by pyreverse')
@click.pass_context
@click.option('--output', '-o', type=click.Path(exists=False), default='__uml__', show_default=True)
@click.option('--format', '-f', default='html', show_default=True)
@click.argument('dir_or_file_path', required=True)
def pyreverse(ctx, output, format, dir_or_file_path):
    """
    corgi_misc pyreverse ~/myenv/lib/python3.10/site-packages/langchain_core/prompts/
    corgi_misc pyreverse ~/myenv/lib/python3.10/site-packages/langchain_core/prompts/chat.py
    """
    from pathlib import Path
    output_path = Path(output)
    if not output_path.exists():
        output_path.mkdir(parents=True)
    output_absolute_path = output_path.absolute().as_posix()
    script = f'pyreverse -f ALL -ASmy -d {output_absolute_path} -o {format} {dir_or_file_path}'
    print(script)
    with time_measurer("Generating UML..."):
        rc, stdout, stderr = run_script(script, capture=True)
    if stdout:
        print(stdout)
    if rc:
        print(red(stderr))
    else:
        print(green(f'UML generated at {output_absolute_path}/classes.{format}'))

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
def renew(ctx):
    assert not is_port_in_use(80), 'Port 80 is in use, please stop the process and try again'

    webroot = from_cwd('__tmp__')
    if not webroot.exists():
        webroot.mkdir()
        os.chmod(webroot, 0o777)

    submit_thread(_run_challenge_server, webroot)
    time.sleep(3)
    # run_script('sudo certbot renew --force-renewal --no-random-sleep-on-renew', realtime=True)
    run_script('sudo certbot renew --force-renewal', realtime=True)

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

def _get_formatters():
    from youtube_transcript_api.formatters import JSONFormatter
    from youtube_transcript_api.formatters import TextFormatter
    from youtube_transcript_api.formatters import WebVTTFormatter
    from youtube_transcript_api.formatters import SRTFormatter

    formatters = {
        'json': JSONFormatter,
        'text': TextFormatter,
        'webvtt': WebVTTFormatter,
        'srt': SRTFormatter,
    }
    return formatters

@youtube.command(help='show youtube video caption')
@click.option('--url', '-u', required=True, help='youtube video url')
@click.option('--sock5-proxy-ip', help='sock5 proxy ip')
@click.option('--sock5-proxy-port', help='sock5 proxy port')
@click.option('--format', '-f', default='text', help='output format')
@click.pass_context
def caption(ctx, url, sock5_proxy_ip, sock5_proxy_port, format):
    video_id = get_param(url, 'v')
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(
            video_id,
            proxies=_proxy_handler(sock5_proxy_ip, sock5_proxy_port)
        )
    except Exception as e:
        perror(str(e))
        return
    transcript = transcript_list.find_transcript(['en'])
    transcript = transcript.fetch()
    formatter = _get_formatters()[format]()
    formatted = formatter.format_transcript(transcript)
    print(formatted)


def _download_caption(url, filename, proxy_handler):
    try:
        video_id = get_param(url, 'v')
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxy_handler or None)
        transcript = transcript_list.find_transcript(['en'])
        transcript = transcript.fetch()
        formatter = _get_formatters()['srt']()
        formatted = formatter.format_transcript(transcript)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(formatted)
    except Exception as e:
        perror(str(e))

def _proxy_handler(sock5_proxy_ip: str, sock5_proxy_port: int) -> Optional[Dict[str, str]]:
    if sock5_proxy_ip and sock5_proxy_port:
        # os.environ['ALL_PROXY'] = f"socks5://{sock5_proxy_ip}:{sock5_proxy_port}"
        socks.set_default_proxy(socks.PROXY_TYPE_SOCKS5, sock5_proxy_ip, sock5_proxy_port)
        socket.socket = socks.socksocket
        return
    proxy_handler = {}
    http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
    https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
    if http_proxy:
        proxy_handler['http'] = http_proxy
    if https_proxy:
        proxy_handler['https'] = https_proxy
    return proxy_handler or None

@youtube.command(help='download youtube video')
@click.option('--url', '-u', required=True, help='youtube video url')
@click.option('--sock5-proxy-ip', help='sock5 proxy ip')
@click.option('--sock5-proxy-port', help='sock5 proxy port', type=int)
@click.option('--time-start', '-s', help="start time, can be expressed in seconds (15.35), in (min, sec), in (hour, min, sec), or as a string: '01:03:05.35'.")
@click.option('--time-end', '-e')
@click.option("--with-audio", is_flag=True, help='create mp3 file at the same time')
@click.option("--dest-dir", '-d', default='', help='destination directory')
@click.pass_context
def download(ctx, url, sock5_proxy_ip, sock5_proxy_port, time_start, time_end, with_audio, dest_dir):
    from pytube import YouTube

    proxy_handler = _proxy_handler(sock5_proxy_ip, sock5_proxy_port)

    def _on_progress_callback(_chunk, _fh, bytes_remaining):
        total = _chunk.filesize
        percent = round((1 - bytes_remaining / total) * 100, 2)
        remaining = round(bytes_remaining / 1024 / 1024)
        print(f"Progress [{percent:3.0f}%], remaining: {remaining:3.0f}M ...\r", end="")
        if bytes_remaining == 0:
            print()

    def _on_complete_callback(_stream, file_path):
        print(f"download completed: {file_path}")
        nonlocal time_start, time_end
        from moviepy.editor import VideoFileClip
        if not time_start:
            if with_audio:
                video = VideoFileClip(file_path)
                video.audio.write_audiofile(modify_extension(file_path, 'mp3'))
            _download_caption(url, modify_extension(file_path, 'srt'), proxy_handler)
            return
        clip_path = add_suffix(file_path, '-clip')
        video = VideoFileClip(file_path).subclip(time_start, time_end)
        video.write_videofile(clip_path)
        if with_audio:
            video.audio.write_audiofile(modify_extension(clip_path, 'mp3'))
        _download_caption(url, modify_extension(clip_path, 'srt'), proxy_handler)

    def __filesize_kb(stream):
        try:
            return int(stream.filesize_kb)
        except Exception:
            return stream._filesize_kb

    if proxy_handler:
        pinfo(f"Using proxy: {proxy_handler}")

    youtube = YouTube(
        url,
        on_progress_callback=_on_progress_callback,
        on_complete_callback=_on_complete_callback,
        proxies=proxy_handler or None,
    )

    streams = youtube.streams.filter(file_extension='mp4',
                                     custom_filter_functions=[
                                         lambda s: s.mime_type.startswith('video'),
                                         lambda s: s.includes_audio_track,
                                     ]).order_by('filesize_kb').desc()
    # print(dir(streams[0]))
    hprint(streams, mappings={
        'itag': ('', lambda x: x.itag),
        'mime_type': ('', lambda x: x.mime_type),
        'fps': ('', lambda x: x.fps),
        # 'progressive': ('', lambda x: x.progressive),
        'type': ('', lambda x: x.type),
        'resolution': ('', lambda x: x.resolution),
        'filesize': ('', __filesize_kb),
        'audio': ('', lambda x: "y" if x.includes_audio_track else ""),
    })
    highest_resolution_video = streams.order_by('resolution').desc().first()
    itag = prompt("Select itag", default=highest_resolution_video.itag)
    pinfo("Start downloading ...")
    with switch_dir(from_cwd('__youtube__', dest_dir)):
        streams.get_by_itag(itag).download()

@cli.command(help='Dictation')
@click.pass_context
@click.argument('filename', type=click.Path(exists=True))
@click.option("--model", "-m", type=click.Choice(['tiny', 'base', 'small']), default='base', show_default=True)
def dictation(ctx, filename, model):
    filename = click.format_filename(filename)
    import whisper
    model = whisper.load_model(model)
    result = model.transcribe(filename)
    with open(modify_extension(filename, 'txt'), 'wb') as f:
        f.write(result['text'].encode('utf-8'))
    print(result["text"])


def main():
    cli()
