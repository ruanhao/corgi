#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from os.path import isfile, join
import sys
from corgi_common import config_logging, pretty_print, bye, as_root, is_root, goodbye
from corgi_common.dateutils import YmdHMS
from corgi_common.scriptutils import run_script
from corgi_common.textutils import extract
import logging
import time
from datetime import datetime
import psutil
import tempfile
import OpenSSL.crypto as crypto

logger = logging.getLogger(__name__)

max_heap = None
native_mem_track = False

ARENA_CHUNK_SIZE = 65536

def info(msg):
    print(msg)
    logger.info(msg)

def _color0(v):
    return click.style(str(v), fg='red')

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

@cli.command(help='Print VM flags (-XX:)', name='VM.flags')
@click.argument('pid', type=int, required=True)
@click.option('--jcmd', '-j', default='jcmd', show_default=True)
def vm_flags(pid, jcmd):
    _check_jcmd(jcmd)
    output = _run_script(f"{jcmd} {pid} VM.flags")
    for line in output.splitlines()[1].split():
        if line.strip():
            print(line)

def _is_native_memory_track_enabled(pid):
    output = _run_script(f'jinfo -flags {pid}')
    return 'NativeMemoryTracking' in output

def _to_bytes(text):
    if text.endswith('KB') or text.endswith('kb') or text.endswith('MB') or text.endswith('mb') or text.endswith('GB') or text.endswith('gb'):
        text = text[0:-1]
    unit = text[-1]
    value = int(text[0:-1])
    if unit in ('B', 'b'):
        return value
    if unit in ('K', 'k'):
        return value * 1024
    if unit in ('M', 'm'):
        return value * 1024 * 1024
    if unit in ('G', 'g'):
        return value * 1024 * 1024 * 1024
    return int(text)

def _numeric(text):
    try:
        f = float(text)
        if f.is_integer():
            return int(f)
        return f
    except Exception:
        return 'nan'

def _gcutil_metric(pid):
    """https://github.com/frohoff/jdk8u-dev-jdk/blob/master/src/share/classes/sun/tools/jstat/resources/jstat_options"""
    output = _run_script(f"jstat -gcutil {pid}")
    lines = output.splitlines()
    headers = lines[0].split()
    values = [_numeric(v) for v in lines[1].split()]
    d = dict(zip(headers, values))
    logger.info(d)
    return d

def _jit_metric(pid):
    output = _run_script(f"jstat -compiler {pid}")
    lines = output.splitlines()
    headers = lines[0].split()
    values = [_numeric(v) for v in lines[1].split()]
    d = dict(zip(headers, values))
    logger.info(d)
    return d

def _round(n, d=1):
    return round(n + 1e-9, d)

def _fetch_metric(pid, proc, with_jit=False):
    global max_heap
    # thread_count = int(_run_script(f'jcmd {pid} Thread.print -l -e | grep "java.lang.Thread.State" | wc -l'))

    thread_count = int(_run_script(f'jcmd {pid} PerfCounter.print | grep java.threads.live=').split('=')[1])
    thread_count_peak = int(_run_script(f'jcmd {pid} PerfCounter.print | grep java.threads.livePeak=').split('=')[1])
    used_heap = _to_bytes(_run_script(f"jcmd {pid} GC.heap_info | grep heap | grep -o 'used [^ ]*'").split()[1])
    max_heap = max_heap or _to_bytes(_run_script(f"jinfo -flags {pid} | grep -o 'MaxHeapSize=[^ ]*'").split('=')[1])

    rss = int(_run_script(f"ps -o rss -p {pid} | tail -1")) * 1024
    gcutil = _gcutil_metric(pid)

    result = {
        'time': datetime.now(),

        'cpu': proc.cpu_percent(),

        'th': thread_count,
        'th_p': thread_count_peak,

        'e_pct': gcutil['E'],
        'ygc': gcutil['YGC'],
        'ygct': gcutil['YGCT'],

        'o_pct': gcutil['O'],
        'fgc': gcutil['FGC'],
        'fgct': gcutil['FGCT'],

        'cgc': gcutil['CGC'],
        'cgct': gcutil['CGCT'],

        'gct': gcutil['GCT'],

        'u_heap': _round(used_heap / 1024 / 1024),
        'm_heap': _round(max_heap / 1024 / 1024),
        'rss': _round(rss / 1024 / 1024),
    }
    if native_mem_track:
        native_mem_info = _run_script(f"jcmd {pid} VM.native_memory summary scale=B")
        total_committed = int(_run_script(f"jcmd {pid} VM.native_memory summary scale=B | grep 'Total:' | grep -o 'committed=[0-9]*$'").split('=')[1])
        result['commit'] = _round(total_committed / 1024 / 1024)
        result['r/c'] = _round(rss / total_committed, 3)  # measure malloc effeciency
        result['native'] = _round(int(_run_script(f"echo '{native_mem_info}' | grep Other | grep -o 'committed=[0-9]*'").split('=')[1]) / 1024 / 1024)
    if with_jit:
        jit = _jit_metric(pid)
        result['jc'] = jit['Compiled']
        result['jf'] = jit['Failed']
        result['jt'] = jit['Time']
    return result


@cli.command(help='Monitor JVM stats')
@click.argument('pid', type=int, required=True)
@click.option('--interval', '-i', default=3, type=int, show_default=True)
@click.option('--with-jit', is_flag=True, show_default=True)
def monitor(pid, interval, with_jit):
    global native_mem_track
    native_mem_track = _is_native_memory_track_enabled(pid)
    logger.info(f"NativeMemoryTracking enabled: {native_mem_track}")
    csv_filename = f'jvm_{pid}.csv'
    proc = psutil.Process(pid)
    h_keys = _fetch_metric(pid, proc).keys()
    if not isfile(csv_filename):
        with open(csv_filename, 'w') as f:
            headers = ",".join(h_keys)
            logger.info(headers)
            f.write(headers + '\n')
    count = 0

    while True:
        metrics = _fetch_metric(pid, proc, with_jit)
        m_values = metrics.values()
        m_str_values = [str(v) for v in m_values]
        metrics_str = ','.join(m_str_values)
        with open(csv_filename, 'a') as f:
            f.write(metrics_str + '\n')
            logger.info(metrics_str)
        metrics['time'] = metrics['time'].strftime('%H:%M:%S')
        output = pretty_print([metrics], json_format=False, tf='plain', raw=True)
        if count % 5 == 0:
            print(output)
        else:
            print(output.splitlines()[1])
        time.sleep(interval - 1)
        count += 1
    pass


@cli.command(help='Print class histogram', name='GC.class_histogram')
@click.argument('pid', type=int, required=True)
@click.option('--jcmd', '-j', default='jcmd', show_default=True)
@click.option('--top', '-n', default=-4, type=int, show_default=True)
def histogram(pid, jcmd, top):
    output = _run_script(f"{jcmd} {pid} GC.class_histogram")
    for line in output.splitlines()[:3 + top]:
        if line.strip():
            print(line)

@cli.command(help='Print string table', name='VM.stringtable')
@click.argument('pid', type=int, required=True)
@click.option('--jcmd', '-j', default='jcmd', show_default=True)
def string_table(**kwargs):
    _string_table(**kwargs)

def _run_script(cmd):
    rc, o, e = run_script(cmd, capture=True)
    if rc != 0:
        bye(e)
    else:
        out = o.strip()
        logger.info(f"{cmd}\n{out}")
        return out

def _string_table(pid, jcmd):
    o = _run_script(f"{jcmd} {pid} VM.stringtable")
    print(o)

@cli.command(help='Dump heap', name='GC.heap_dump')
@click.argument('pid', type=int, required=True)
@click.option('--jcmd', '-j', default='jcmd', show_default=True)
@click.option('--file', '-f', "filepath")
def heap_dump(pid, jcmd, filepath):
    if not filepath:
        # tempdir = tempfile.mkdtemp()
        tempdir = tempfile.gettempdir()
        filepath = join(tempdir, f"{YmdHMS()}.hprof")
    print(_run_script(f"{jcmd} {pid} GC.heap_dump {filepath}"))
    pass

@cli.command(help='Print heap configuration', name='jmap.heap')
@click.argument('pid', type=int, required=True)
def heap_info(**kwargs):
    _jmap(**kwargs)

@as_root
def _jmap(pid):
    rc, stdout, stderr = run_script(f'jhsdb jmap --heap --pid {pid}', capture=True)
    if rc == 0:
        logger.info(f"Heap info for jvm {pid}\n{stdout}")
        print(stdout)
    else:
        logger.error(f"Failed to get heap info for jvm {pid}\nstderr")


@cli.command(help='Parse jvm stack file')
@click.option('-x', is_flag=True)
@click.option('--stack-file', help='jstack file to work with', type=click.File('r'), default=sys.stdin, show_default=True)
def parse_stack(x, stack_file):
    with stack_file:
        stack_info = stack_file.read()
        _print_stack_info(stack_info, x=x)
    pass

@cli.command(help='Show jvm native memory info', name='VM.native_memory')
@click.argument('pid', type=int, required=True)
@click.option('--jcmd', '-j', default='jcmd', show_default=True)
@click.option('-b', is_flag=True)
@click.option('-m', is_flag=True)
@click.option('-g', is_flag=True)
@click.option('--raw', is_flag=True)
@click.option('--max-guess-span', type=int, default=4, show_default=True)
def native_memory(pid, jcmd, b, m, g, raw, max_guess_span):
    unit = 'KB'
    s = 1024
    if g:
        unit = 'GB'
        s = 1024 * 1024 * 1024
    if m:
        unit = 'MB'
        s = 1024 * 1024
    if b:
        unit = 'B'
        s = 1
    _check_jcmd(jcmd)
    output = _run_script(f"{jcmd} {pid} VM.native_memory summary scale={unit}")

    if raw:
        print(output)
    else:
        rss = None
        if sys.platform == 'linux':
            rss_bytes = int(_run_script(f'ps -o rss -p {pid} -h').strip()) * 1024
            rss = int(rss_bytes / s)
            logger.info(f"RSS for {pid}: {rss}{unit}")
        _parse_native_mem(output, rss, unit)

    if sys.platform == 'linux':
        if is_root():
            kbytes_array = []
            for line in _run_script(f"pmap -x {pid} | grep anon | awk '{{print $2;}}'").split():
                kbytes_array.append(int(line))

            guesses = [_guess_by(kbytes_array, d) for d in range(1, max_guess_span + 1)]
            logger.info(f"guesses: {[i for i in enumerate(guesses, 1)]}")
            print(f"Guess for number of arena chunks(glib malloc): {sum(guesses)}")
        else:
            goodbye("Please run as root to see arena chunk info")


def _guess_by(array, div):
    tries = []
    for i in range(0, div):
        count = _do_guess(_group_every(array[i:] + [0] * i, div))
        tries.append(count)
    m = max(tries)
    logger.info(f"tries for div {div}: {tries}, max: {m}")
    return m

def _do_guess(couples):
    count = 0
    for couple in couples:
        if sum(couple) == ARENA_CHUNK_SIZE:
            logger.info(f"found couple: {couple}({len(couple)})")
            count += 1
    return count

def _group_every(lst, N):
    return [lst[n:n + N] for n in range(0, len(lst), N)]

# https://stackoverflow.com/questions/53451103/java-using-much-more-memory-than-heap-size-or-size-correctly-docker-memory-limi
@cli.command(help='Parse jvm native memory from file/stdin')
@click.option('--input', '-i', 'input_file', help='file to work with', type=click.File('r'), default=sys.stdin, show_default=True)
def native_memory_parse(input_file):
    with input_file:
        txt = input_file.read()
        _parse_native_mem(txt)
    pass

def _parse_native_mem(txt, rss=None, u='KB'):
    logger.info(f"Native Memory info: \n{txt}")
    total_reserved = None
    total_committed = None
    result = []
    unit = None
    for line in txt.splitlines():
        if line.startswith('-'):
            groups = extract(r'^-\s*(.*) \(reserved=([0-9]*).*, committed=([0-9]*).*\)$', line)
            if groups:
                name, r, c = groups
                result.append({
                    'n': name,
                    'r': r,
                    'c': c
                })
        elif line.startswith('Total'):
            # groups = extract(r'^Total: reserved=([0-9]*)([GMKB]?), committed=([0-9]*).*$', line)
            groups = extract(r'^Total: reserved=([0-9]*)(.*), committed=([0-9]*).*$', line)
            # print(groups)
            if groups:
                total_reserved, unit, total_committed = groups
    unit = unit or u
    r = 0
    c = 0
    for i in result:
        if i['n'] == 'Other':
            i['n'] += '(DirectBuffer)'
        if i['n'] == 'Symbol':
            i['n'] += '(string table,constant pool)'
        if i['n'] == 'Arena Chunk':
            i['n'] += '(Memory used by chunks in the arena chunk pool)'
        r += int(i['r'])
        c += int(i['c'])
    pretty_print(sorted(result, key=lambda x: int(x['c']), reverse=True), mappings={
        'Module': 'n',
        f'reserved({unit})': 'r',
        f'committed({unit})': 'c',
    })
    print()
    t_r = f"{total_reserved}{unit}"
    t_c = f"{total_committed}{unit}"
    if not total_reserved:
        t_r = 'n/a'
        info("NMT not enabled? (-XX:NativeMemoryTracking=detail)")
    if not total_committed: t_c = 'n/a'
    if rss:
        print(f"Total: reserved={t_r}, committed={t_c}, rss={rss}{unit}")
    else:
        print(f"Total: reserved={t_r}, committed={t_c}")
    # print(f"Total(calculated): reserved={r}{unit}, committed={c}{unit}")


@cli.command(help='Show jvm stack info on Linux platform', name='Thread.print')
@click.argument('pid', type=int, required=True)
@click.option('--jstack-bin', '-j', default='jstack', show_default=True)
@click.option('--jcmd', default='jcmd', show_default=True)
@click.option('--top', '-n', default=-1, type=int, show_default=True)
@click.option('-x', is_flag=True)
@click.option('--raw', is_flag=True)
@click.option('--force-psutil', is_flag=True)
def thread_info(**kwargs):
    _jstack(**kwargs)
    pass

def _print_stack_info(stack_info, t_infos={}, x=False, top=-1):
    lines = stack_info.splitlines()
    lines_len = len(lines)
    if lines_len == 0:
        bye("No stack info available")
    found_deadlock = False
    i = 0
    while i < lines_len:
        line = lines[i]
        i += 1
        if 'Found' in line and 'deadlock' in line:
            found_deadlock = True
        if 'nid=' in line:
            daemon = 'daemon' in line
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
                the_info = {
                    'ntid': int(tid_hex, 16),
                    'ntid_hex': tid_hex,
                    'tname': thread_name,
                    **t_info,
                }
                t_infos[tid_hex] = the_info
            else:
                the_info = t_infos[t_info['nid']]
                the_info['tname'] = thread_name
                the_info.update(t_info)
            # guess state
            if 'runnable' in line:
                the_info['state'] = 'RUNNABLE'
            if 'waiting' in line:
                the_info['state'] = 'WAITING'
            next_line = lines[i]
            the_info['daemon'] = daemon or ''
            if 'java.lang.Thread.State' in next_line:
                the_info['state'] = next_line.split(':')[1].strip()

    for k, v in t_infos.copy().items():
        if 'tname' not in v or not v['tname']:
            del t_infos[k]
    pretty_print(list(t_infos.values())[:top], mappings={
        'name': ('tname', _compress),
        # 'tid': 'ntid',
        'daemon': "daemon",
        'tid (hex)': 'ntid_hex',
        'heap': 'allocated',    # ever allocated heap
        'classes': 'defined_classes',
        'cpu': 'cpu',
        'clock': 'elapsed',
        '%cpu': 'pcpu',
        'state': 'state',
    }, x=x)
    if found_deadlock:
        print(_color0('Deadlock found !!!'))

def _check_jcmd(jcmd):
    if jcmd == 'jcmd':
        rc, _, _ = run_script('which jstack', capture=True)
        if rc != 0:
            rc, stdout, _ = run_script("""java -version 2>&1 | sed -n ';s/.* version "\(.*\)\.\(.*\)\..*".*/\1/p;'""", capture=True)
            if rc == 0:
                java_version = stdout.strip()
            else:
                java_version = '<version>'
            bye(f"jcmd command not found, try: apt install openjdk-{java_version}-jdk-headless && apt install openjdk-{java_version}-dbg")
    elif not isfile(jcmd):
        bye(f"{jcmd} not found")

# @as_root
def _jstack(pid, jstack_bin, jcmd, x, top, force_psutil, raw):
    _check_jcmd(jcmd)
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
                'pcpu': _round(float((t.system_time + t.user_time) / total_time), 2)
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
    # rc, stack_info, stderr = run_script(f"{jstack_bin} -l -e {pid}", capture=True)
    rc, stack_info, stderr = run_script(f"{jcmd} {pid} Thread.print -l -e", capture=True)
    if rc != 0:
        logger.error(stderr)
        bye(f"Failed to get stack info: {stderr}")
    logger.info(f"jstack for {pid}: \n{stack_info}")
    if raw:
        print(stack_info)
        return
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

@cli.command(short_help='generate script to import cert to java keystore')
@click.argument('cert', type=click.File('rb'), required=False)
@click.option('--test', '-t', is_flag=True, help='show script to verify')
@click.option('--hostname', '-h')
def keytool_import(cert, test, hostname):
    """\b
    generate script to import cert to java keystore.
    default password is: changeit"""
    if test:
        assert hostname, 'must specify <hostname> when doing test'
        # output = f"""jshell <(echo -e 'import java.net.http.*;\\nvar client = HttpClient.newHttpClient();\\nvar uri = new URI("https://{hostname}");\\nvar request = HttpRequest.newBuilder().uri(uri).build();\\nvar response = client.send(request, HttpResponse.BodyHandlers.ofString());\\nSystem.out.println(response.body());\\n/exit')"""
        output = f"""jshell <(echo -e '
        import java.net.http.*;
        var client = HttpClient.newHttpClient();
        var uri = new URI("https://{hostname}");
        var request = HttpRequest.newBuilder().uri(uri).build();
        var response = client.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println(response.body());
\\n/exit')"""
        print(output)
        return
    assert cert, 'must specify <cert>'
    x509 = crypto.load_certificate(crypto.FILETYPE_PEM, cert.read())
    cn = x509.get_subject().CN
    alias = cn
    output = f"""export JAVA_HOME=`jshell <(echo -e 'java.lang.System.out.println(java.lang.System.getProperty("java.home"))\\n/exit')`
keytool -delete -noprompt -trustcacerts -alias {alias} -keystore $JAVA_HOME/lib/security/cacerts || true
keytool -importcert -file {cert.name} -keystore $JAVA_HOME/lib/security/cacerts -alias {alias}"""
    print(output)

def main():
    config_logging('corgi_jvm')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
