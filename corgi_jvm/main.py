#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from os.path import isfile
import sys
from corgi_common import config_logging, pretty_print, get, bye, as_root
from corgi_common.scriptutils import run_script
import logging
import psutil
import select
from pprint import pprint

logger = logging.getLogger(__name__)

def info(msg):
    print(msg)
    logger.info(msg)

def _color(v, func):
    if func(v):
        return click.style(str(v), fg='red')
    else:
        return str(v)


@click.group(help="CLI tool for JVM diagnose")
def cli():
    pass


def _compress(s, length=30):
    if not s:
        return 'n/a'
    if len(str(s)) <= length:
        return str(s)
    return str(s)[:length] + "..."

@cli.command(help='Parse jvm stack file')
@click.option('-x', is_flag=True)
@click.option('--stack-file', help='jstack file to work with', type=click.File('r'), default=sys.stdin, show_default=True)
def parse_stack(x, stack_file):
    with stack_file:
        stack_info = stack_file.read()
        _print_stack_info(stack_info, x=x)
    pass

@cli.command(help='Show jvm stack info on Linux platform')
@click.option('--pid', '-p', type=int, required=True)
@click.option('--jstack-bin', '-j', default='jstack', show_default=True)
@click.option('--top', '-n', default=-1, type=int, show_default=True)
@click.option('-x', is_flag=True)
@click.option('--force-psutil', is_flag=True)
def jstack(**kwargs):
    _jstack(**kwargs)
    pass

def _print_stack_info(stack_info, t_infos={}, x=False, top=-1):
    for line in stack_info.splitlines():
        if 'nid=' in line:
            first_quote_idx = line.index('"')
            second_quote_idx = line.index('"', first_quote_idx + 1)
            thread_name = line[first_quote_idx + 1:second_quote_idx - first_quote_idx]
            tokens = line[second_quote_idx + 1:].split()
            t_info = {}
            for token in tokens:
                if '=' in token:
                    k, v = token.split('=')
                    t_info[k] = v
            tid_hex = t_info['nid']
            if tid_hex not in t_infos:
                t_infos[tid_hex] = {
                    'ntid': int(tid_hex, 16),
                    'ntid_hex': tid_hex,
                    'tname': thread_name,
                    **t_info,
                }
            else:
                the_info = t_infos[t_info['nid']]
                the_info['tname'] = thread_name
                the_info.update(t_info)
    for k, v in t_infos.copy().items():
        if 'tname' not in v or not v['tname']:
            del t_infos[k]
    pretty_print(list(t_infos.values())[:top], mappings={
        'name': ('tname', _compress),
        'tid': 'ntid',
        'tid (hex)': 'ntid_hex',
        'allocated (heap)': 'allocated',
        'classes': 'defined_classes',
        'cpu': 'cpu',
        'clock': 'elapsed',
        '%cpu': 'pcpu',
    }, x=x)

@as_root
def _jstack(pid, jstack_bin, x, top, force_psutil):
    rc, stdout, _ = run_script("""java -version 2>&1 | sed -n ';s/.* version "\(.*\)\.\(.*\)\..*".*/\1/p;'""", capture=True)
    if rc == 0:
        java_version = stdout.strip()
    else:
        java_version = '<version>'
    if jstack_bin == 'jstack':
        rc, _, _ = run_script('which jstack', capture=True)
        if rc != 0:
            bye(f"jstack command not found, try: apt install openjdk-{java_version}-jdk-headless && apt install openjdk-{java_version}-dbg")
    elif not isfile(jstack_bin):
        bye(f"{jstack_bin} not found")
    try:
        proc = psutil.Process(pid)
    except Exception:
        bye(f"Process {pid} not found.")
    logger.info(f"Profiling stack info for java pid {pid}")
    rc, stdout, stderr = run_script(f"ps H -eo pid,tid,pcpu --sort -pcpu | grep {pid}", capture=True)
    t_infos = {}
    if (force_psutil or rc != 0) and sys.platform != 'darwin':
        logger.error(f"Cannot get native thread info from ps ({rc})\n{stderr}")
        total_time = sum(proc.cpu_times())
        logger.info(f"total cpu time: {total_time}")
        threads = sorted(proc.threads(), key=lambda t: (t.system_time + t.user_time) / total_time, reverse=True)  # MAC will crash at this line
        for t in threads:
            tid = t.id
            tid_hex = hex(tid)
            t_infos[tid_hex] = {
                'ntid': tid,
                'ntid_hex': tid_hex,
                'pcpu': round(float((t.system_time + t.user_time) / total_time), 2)
            }
    else:
        for line in (stdout or '').splitlines():
            parent_pid, native_tid, pct = line.split()
            if parent_pid == native_tid:
                continue
            tid_hex = hex(int(native_tid))
            t_infos[tid_hex] = {
                'ntid': int(native_tid),
                'pcpu': float(pct),
                'ntid_hex': tid_hex
            }
    rc, stack_info, stderr = run_script(f"{jstack_bin} -l -e {pid}", capture=True)
    if rc != 0:
        logger.error(stderr)
        bye(f"Failed to get stack info: {stderr}")
    logger.info(f"jstack for {pid}: \n{stack_info}")
    _print_stack_info(stack_info, t_infos=t_infos, x=x, top=top)
    # for line in stack_info.splitlines():
    #     if 'nid=' in line:
    #         first_quote_idx = line.index('"')
    #         second_quote_idx = line.index('"', first_quote_idx + 1)
    #         thread_name = line[first_quote_idx + 1:second_quote_idx - first_quote_idx]
    #         tokens = line[second_quote_idx + 1:].split()
    #         t_info = {}
    #         for token in tokens:
    #             if '=' in token:
    #                 k, v = token.split('=')
    #                 t_info[k] = v
    #         tid_hex = t_info['nid']
    #         if tid_hex not in t_infos:
    #             t_infos[tid_hex] = {'ntid_hex': tid_hex, 'tname': thread_name, **t_info}
    #         else:
    #             the_info = t_infos[t_info['nid']]
    #             the_info['tname'] = thread_name
    #             the_info.update(t_info)
    # for k, v in t_infos.copy().items():
    #     if 'tname' not in v or not v['tname']:
    #         del t_infos[k]
    # pretty_print(list(t_infos.values())[:top], mappings={
    #     'name': ('tname', _compress),
    #     'tid': 'ntid',
    #     'tid (hex)': 'ntid_hex',
    #     'allocated (heap)': 'allocated',
    #     'classes': 'defined_classes',
    #     'cpu': 'cpu',
    #     'clock': 'elapsed',
    #     '%cpu': 'pcpu',
    # }, x=x)
    pass

def main():
    config_logging('corgi_jvm')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
