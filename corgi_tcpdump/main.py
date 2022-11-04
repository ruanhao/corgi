#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from icecream import ic
from corgi_common.scriptutils import run_script
from corgi_common import config_logging, pretty_print
from corgi_common.textutils import extract_mp
import logging

logger = logging.getLogger(__name__)

def info(msg):
    print(msg)
    logger.info(msg)

def warning(msg):
    click.secho(msg, fg='yellow')
    logger.warning(msg)

def _color(v, func):
    if func(v):
        return click.style(str(v), fg='red')
    else:
        return str(v)

def _float(s):
    return float(s.replace(',', ''))

def _int(s):
    return int(_float(s))

def _parse_convs(stdout):
    convs = []
    for line in stdout.splitlines():
        if '<->' not in line:
            continue
        tokens = line.split()
        ic(tokens)
        (
            src,
            _arrow,
            dst,
            d_to_s_frames,
            d_to_s_bytes,
            d_to_s_bytes_scale,
            s_to_d_frames,
            s_to_d_bytes,
            s_to_d_types_scale,
            _total_frames,
            _total_bytes,
            _total_types_scale,
            relative_start,
            duration
        ) = tokens

        d_to_s_frames = _int(ic(d_to_s_frames))
        d_to_s_bytes = _int(d_to_s_bytes)
        s_to_d_frames = _int(s_to_d_frames)
        s_to_d_bytes = _int(s_to_d_bytes)
        relative_start = _float(ic(relative_start))
        duration = _float(duration)

        if d_to_s_bytes_scale == 'kB':
            d_to_s_bytes *= 1024
        elif d_to_s_bytes_scale == 'MB':
            d_to_s_bytes *= (1024 * 1024)

        if s_to_d_types_scale == 'kB':
            s_to_d_bytes *= 1024
        elif s_to_d_types_scale == 'MB':
            s_to_d_bytes *= (1024 * 1024)

        # ic(src)
        # ic(_arrow)
        # ic(dest)
        # ic(d_to_s_frames)
        # ic(d_to_s_bytes)
        # ic(d_to_s_bytes_scale)
        # ic(s_to_d_frames)
        # ic(s_to_d_bytes)
        # ic(s_to_d_types_scale)
        # ic(relative_start)
        # ic(duration)
        # exit()

        convs.append({
            'src': src,
            'dst': dst,
            's_d_frames': s_to_d_frames,
            's_d_bytes': s_to_d_bytes,
            'd_s_frames': d_to_s_frames,
            'd_s_bytes': d_to_s_bytes,
            'relative_start': relative_start,
            'duration': duration
        })

    return sorted(convs, key=lambda c: c['relative_start'])

@click.group(help="CLI tool for tcpdump/tshark")
def cli():
    pass

@cli.command(help='Show conversations')
@click.argument('pcap', type=click.Path(exists=True, file_okay=True, readable=True, resolve_path=True))
@click.option('--type', '-t', '_type', type=click.Choice(['tcp', 'udp', 'eth', 'ip']), default='tcp', show_default=True)
@click.option('--dry', is_flag=True)
@click.option('-x', is_flag=True)
@click.option('--raw', is_flag=True)
def conversations(pcap, dry, _type, x, raw):
    cmd = f'tshark -n -q -r {pcap} -z conv,{_type}'
    if dry:
        print(cmd)
        return
    rc, stdout, stderr = run_script(cmd, capture=True)
    ic(rc)
    if raw:
        print(stdout)
        return
    convs = _parse_convs(stdout)
    pretty_print(convs, mappings={
        'Src': 'src',
        'Dst': 'dst',
        'Frames(->)': 's_d_frames',
        'Bytes(->)': 's_d_bytes',
        'Frames(<-)': 'd_s_frames',
        'Bytes(<-)': 'd_s_bytes',
        'Frames': ('', lambda x: x['s_d_frames'] + x['d_s_frames']),
        'Bytes': ('', lambda x: x['s_d_bytes'] + x['d_s_bytes']),
        'Relative Time': 'relative_start',
        'Duration(s)': 'duration',
    }, x=x, numbered=True, offset=-1)

    # print(stdout)

def _decode_hex(h):
    lf = 10
    cr = 13
    prev = -1

    def _chr(v):
        nonlocal prev
        p = prev
        prev = v
        if v not in [lf, cr] and (v <= 32 or v >= 127):
            return '.'
        if v == cr and p == lf:
            return '\n'
        try:
            return chr(v)
        except Exception:
            return '.'
    return ''.join([_chr(int(''.join(c), 16)) for c in zip(h[0::2], h[1::2])])
    # return bytes.fromhex(ic(h)).decode("ASCII")

@cli.command(help='Follow stream')
@click.argument('pcap', type=click.Path(exists=True, file_okay=True, readable=True, resolve_path=True))
@click.option('--http', is_flag=True)
@click.option('--color', is_flag=True)
@click.option('--dry', is_flag=True)
@click.option('--raw', is_flag=True)
@click.option('--stream', '-s', default=0, type=int, show_default=True)
def follow(pcap, http, color, dry, stream, raw):
    cmd = f'tshark -n -q -r {pcap} -z conv,tcp'
    rc, stdout, stderr = run_script(cmd, capture=True)
    ic(rc)
    convs = _parse_convs(stdout)
    stream_info = convs[stream]
    src = stream_info['src']
    dst = stream_info['dst']
    src_ip, src_port = src.split(':')
    dst_ip, dst_port = dst.split(':')

    cmd = f'tshark -r {pcap} -Y "tcp.stream=={stream} && echo.data" -d tcp.port=={src_port},echo -d tcp.port=={dst_port},echo -T fields -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport -e echo.data'
    t = 'http' if http else 'tcp'
    if raw:
        cmd = f'tshark -r {pcap} -q -z follow,{t},ascii,{stream}'
    if dry:
        print(cmd)
        return
    rc, stdout, stderr = run_script(cmd, capture=True)
    ic(rc)
    if raw:
        print(stdout)
        return
    # decode hex
    for line in stdout.splitlines():
        _src_ip, _dst_ip, sport, dport, hex_data = ic(line.split())
        data = _decode_hex(hex_data)
        if ic(sport) == ic(src_port):   # s -> d
            direction = '->'
            c = 'red'
        else:                   # d -> s
            direction = '<-'
            c = 'green'

        if color:
            click.secho(data, fg=c)
        else:
            print(f"[{src} {direction} {dst}]")
            click.echo(data)
    pass

def _analyze_summary(pcap, dry=False):
    cmd = f"capinfos {pcap}"
    rc, stdout, stderr = run_script(cmd, capture=True)
    capture_duration_secs = _int(extract_mp(r'Capture duration:\s*(.*) seconds', stdout)[0])

    av_data_byte_rate, av_data_byte_rate_scale = extract_mp(r'Data byte rate:\s*(.*) (kBps|bytes/s)', stdout)[0]
    av_data_byte_rate = _float(av_data_byte_rate)
    assert av_data_byte_rate_scale in ['kBps', 'bytes/s']
    if av_data_byte_rate_scale == 'kBps':
        av_data_byte_rate *= 1024

    av_pkt_rate = _float(extract_mp(r'Average packet rate:\s*(.*) packets/s', stdout)[0])

    av_pkt_size, av_pkt_size_scale = extract_mp(r'Average packet size:\s*(.*) (bytes)', stdout)[0]
    assert av_pkt_size_scale in ['bytes']
    av_pkt_size = _float(av_pkt_size)

    if dry:
        print(cmd)
        return

    ic(capture_duration_secs, 'seconds')
    ic(av_data_byte_rate, 'bps')
    ic(av_pkt_rate, 'pps')
    ic(av_pkt_size, 'bytes')

    click.echo("======= Cap Info =======")
    click.echo(f"Average packet size: {av_pkt_size} bytes")
    click.echo(f"Average packet rate: {av_pkt_rate} packets/s")
    if av_data_byte_rate > 1024 * 8:
        click.echo(f"Average data rate: {av_data_byte_rate * 8 / 1024:.2f} Kb/s")
    else:
        click.echo(f"Average data rate: {av_data_byte_rate} bytes/s")

def _analyze_tcp(pcap, stream=None, dry=False):

    def _frames_bytes(stdout):
        for line in stdout.splitlines():
            if '<>' not in line:
                continue
            tokens = line.replace('|', '').split()
            return _int(tokens[-2]), _int(tokens[-1])
        pass

    stream_filter = f" -R 'tcp.stream=={stream}' -2 " if stream is not None else ''
    retransmission_cmd = f'tshark -r {pcap} -n -q -z io,stat,0,tcp.analysis.retransmission' + stream_filter
    out_of_order_cmd = f'tshark -r {pcap} -n -q -z io,stat,0,tcp.analysis.out_of_order' + stream_filter

    if dry:
        click.echo(retransmission_cmd)
        click.echo(out_of_order_cmd)
        return

    rc0, stdout0, stderr0 = run_script(retransmission_cmd, capture=True)
    frames0, bytes0  = _frames_bytes(stdout0)
    ic(rc0, frames0, bytes0)

    rc1, stdout1, stderr1 = run_script(out_of_order_cmd, capture=True)
    frames1, bytes1  = _frames_bytes(stdout1)
    ic(rc1, frames1, bytes1)

    print("===== TCP Analysis =====")
    click.secho(f"Retransmission: {frames0} frames ({bytes0} bytes)", fg='red' if frames0 > 0 else None)
    click.secho(f"Out of order: {frames1} frames ({bytes1} bytes)", fg='red' if frames1 > 0 else None)


@cli.command(help='Analyze pcap')
@click.argument('pcap', type=click.Path(exists=True, file_okay=True, readable=True, resolve_path=True))
@click.option('--dry', is_flag=True)
@click.option('--stream', '-s', required=False)
def analyze(pcap, dry, stream):
    ic(pcap)
    _analyze_summary(pcap, dry)
    _analyze_tcp(pcap, stream, dry)


def main():
    config_logging('corgi_tcpdump')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
