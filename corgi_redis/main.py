#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging, pretty_print, get
from corgi_common.dateutils import pretty_duration
from corgi_common.scriptutils import try_run_script_as_root
import redis
import datetime
import logging
from pprint import pprint

def _color(text):
    return click.style(f'{text}', fg='red')


logger = logging.getLogger(__name__)

@click.group(help="CLI tool for Redis")
def cli():
    pass

def _using_swap(process_id):
    script = f'''cat /proc/{process_id}/smaps | grep Swap: | awk '{{print $2;}}' | grep -v '^0$\|^4$' | wc -l'''
    try:
        rc, stdout, _ = try_run_script_as_root(script, capture=True)
        return int(stdout.strip()) != 0
    except Exception as e:
        logger.error(f"Error when checking if using swap: {e}")
    pass

def _get_cluster_metrics(host, port, password):
    from redis.cluster import RedisCluster, ClusterNode
    nodes = [ClusterNode(host, port)]
    rc = RedisCluster(startup_nodes=nodes, password=password, decode_responses=True)
    cluster_stats = rc.cluster_info()
    # pprint(rc.cluster_nodes())
    # pprint(rc.cluster_slots())
    # pprint(cluster_stats)
    cluster_state = cluster_stats['cluster_state']
    if cluster_state != 'ok':
        cluster_state = _color(cluster_state)
    cluster_slots_pfail = int(cluster_stats['cluster_slots_pfail'])
    if cluster_slots_pfail != 0:
        cluster_slots_pfail = _color(cluster_slots_pfail)
    cluster_slots_fail = int(cluster_stats['cluster_slots_fail'])
    if cluster_slots_fail != 0:
        cluster_slots_fail = _color(cluster_slots_fail)

    cat = 'CLUSTER'
    return [
        {
            'metric': 'cluster_size',
            'value': cluster_stats['cluster_size'],
            'desc': 'Number of masters',
            'category': cat,
        },
        {
            'metric': 'cluster_known_nodes',
            'value': cluster_stats['cluster_known_nodes'],
            'desc': 'Number of all nodes',
            'category': cat,
        },
        {
            'metric': 'cluster_state',
            'value': cluster_state,
            'desc': 'Cluster state',
            'category': cat,
        },
        {
            'metric': 'cluster_slots_pfail',
            'value': cluster_slots_pfail,
            'desc': 'There MAYBE some unreachable node(s)',
            'category': cat,
        },
        {
            'metric': 'cluster_slots_fail',
            'value': cluster_slots_fail,
            'desc': 'There MUST be some unreachable node(s)',
            'category': cat,
        },
    ]

@cli.command(help='Show redis usage info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('--password')
@click.option('--show-all', is_flag=True)
@click.option('-x', is_flag=True)
def info(host, port, password, show_all, x):
    r = redis.Redis(host=host, port=port, password=password)
    metrics = []
    dbsize = r.dbsize()
    info_stats = r.info()
    if show_all:
        pprint(info_stats)
        return
    rejected_connections = info_stats['rejected_connections']
    if rejected_connections > 0:
        rejected_connections = click.style(f'{rejected_connections}', fg='red')
    if get(info_stats, 'maxmemory', 0) and int(info_stats['used_memory']) / get(info_stats, 'maxmemory', 0) > 0.8:
        info_stats['used_memory_human'] = _color(info_stats['used_memory_human'])
    if info_stats['rdb_last_bgsave_status'] != 'ok':
        info_stats['rdb_last_bgsave_status'] = _color(info_stats['rdb_last_bgsave_status'])
    if info_stats['aof_last_bgrewrite_status'] != 'ok':
        info_stats['aof_last_bgrewrite_status'] = _color(info_stats['aof_last_bgrewrite_status'])
    if info_stats['rdb_last_bgsave_time_sec'] > 0:
        info_stats['rdb_last_bgsave_time_sec'] = _color(info_stats['rdb_last_bgsave_time_sec'])
    if info_stats['latest_fork_usec'] > (info_stats['used_memory'] / 1024 / 1024 / 1024 * 20 * 1000):  # 20ms/GB
        info_stats['latest_fork_usec'] = _color(info_stats['latest_fork_usec'])
    if info_stats.get('aof_delayed_fsync', 0) > 0:
        info_stats['aof_delayed_fsync'] = _color(info_stats['aof_delayed_fsync'])

    mem_fragmentation_ratio = get(info_stats, 'mem_fragmentation_ratio', -1)
    using_swap = mem_fragmentation_ratio < 1 or _using_swap(info_stats['process_id'])
    if using_swap is None:
        using_swap = 'n/a'
    if using_swap is True:
        using_swap = _color(using_swap)
    metrics += [
        {
            'category': 'SERVER',
            'metric': "",
            'desc': "Check if using swap",
            'value': using_swap,
        }
    ]
    if mem_fragmentation_ratio < 1 or mem_fragmentation_ratio > 1.5:
        mem_fragmentation_ratio = _color(mem_fragmentation_ratio)

    evicted_keys = get(info_stats, 'evicted_keys', 0)
    if evicted_keys > 0:
        evicted_keys = _color(evicted_keys)
    metrics += [
        {'metric': 'redis_version', 'value': info_stats['redis_version'], 'desc': 'Version', 'category': 'SERVER'},
        {'metric': 'uptime_in_seconds', 'value': pretty_duration(info_stats['uptime_in_seconds']), 'desc': 'Uptime', 'category': 'SERVER'},

        {'metric': 'redis_mode', 'value': info_stats['redis_mode'], 'desc': 'Running mode', 'category': 'REPLICA'},
        {'metric': 'role', 'value': info_stats['role'], 'desc': 'Master/Slave', 'category': 'REPLICA'},

        {'metric': 'used_memory_human', 'value': info_stats['used_memory_human'], 'desc': 'Memory consumed by all internal data structures', 'category': 'Memory'},
        {'metric': 'used_memory_peak_human', 'value': info_stats['used_memory_peak_human'], 'desc': 'Mem Peak', 'category': 'Memory'},
        {'metric': 'used_memory_rss_human', 'value': info_stats.get('used_memory_rss_human', -1), 'desc': 'Physical memory from OS perspective of view', 'category': 'Memory'},
        {'metric': 'maxmemory_human', 'value': info_stats.get('maxmemory_human', -1), 'desc': 'Max memory allowed for `used_memory`', 'category': 'Memory'},
        {'metric': 'maxmemory_policy', 'value': info_stats.get('maxmemory_policy', 'n/a'), 'desc': 'Max memory Policy', 'category': 'Memory'},
        {'metric': 'mem_fragmentation_ratio', 'value': mem_fragmentation_ratio, 'desc': 'used_mem_rss/used_mem, <1: using swap, >1.5: allocator not return mem to OS', 'category': 'Memory'},
        {'metric': 'evicted_keys', 'value': evicted_keys, 'desc': 'Evicted keys according to maxmemory_policy', 'category': 'Memory'},

        {'metric': 'total_connections_received', 'value': info_stats['total_connections_received'], 'desc': 'Total connections ever', 'category': 'TCP'},
        {'metric': 'rejected_connections', 'value': info_stats['rejected_connections'], 'desc': 'Ever rejected connections', 'category': 'TCP'},

        {'metric': 'dbsize', 'value': dbsize, 'desc': 'Total size of keys', 'category': 'DATA'},

        {'metric': 'rdb_last_save_time', 'value': datetime.datetime.fromtimestamp(int(info_stats['rdb_last_save_time'])), 'desc': 'Last time of saving snapshot', 'category': 'RDB'},
        {'metric': 'rdb_last_bgsave_status', 'value': info_stats['rdb_last_bgsave_status'], 'desc': 'Last saving snapshot status', 'category': 'RDB'},
        {'metric': 'rdb_last_bgsave_time_sec', 'value': info_stats['rdb_last_bgsave_time_sec'], 'desc': 'Time consumption of last saving snapshot', 'category': 'RDB'},
        {'metric': 'latest_fork_usec', 'value': info_stats['latest_fork_usec'], 'desc': 'Time consumption of last fork', 'category': 'RDB/AOF'},

        {'metric': 'aof_enabled', 'value': info_stats['aof_enabled'] == 1, 'desc': 'AOF enabled', 'category': 'AOF'},
        {'metric': 'aof_last_bgrewrite_status', 'value': info_stats['aof_last_bgrewrite_status'], 'desc': 'Last AOF status', 'category': 'AOF'},
        {'metric': 'aof_delayed_fsync', 'value': info_stats.get('aof_delayed_fsync', -1), 'desc': 'Timeout(2s) when waiting for ASYNC fsync to complete after writing to AOF buffer', 'category': 'AOF'},
    ]

    if get(info_stats, 'role') == 'master':
        metrics.append({'metric': 'master_repl_offset', 'value': get(info_stats, 'master_repl_offset'), 'desc': "Offset as master", 'category': 'REPLICA'})
        metrics.append({'metric': 'connected_slaves', 'value': info_stats['connected_slaves'], 'desc': 'Connected slaves', 'category': 'REPLICA'})
    if get(info_stats, 'role') == 'slave':
        master_last_io_seconds_ago = get(info_stats, 'master_last_io_seconds_ago', -1)
        if master_last_io_seconds_ago > 10:
            master_last_io_seconds_ago = _color(master_last_io_seconds_ago)
        metrics += [
            {'metric': 'slave_repl_offset', 'value': get(info_stats, 'slave_repl_offset'), 'desc': "Offset as slave", 'category': 'REPLICA'},
            {'metric': 'master_last_io_seconds_ago', 'value': master_last_io_seconds_ago, 'desc': "Lag from last master ping (every 10s)", 'category': 'REPLICA'},
        ]
    for i in range(0, get(info_stats, 'connected_slaves', 0)):
        slave_offset = get(info_stats, f'slave{i}.offset')
        slave_lag = get(info_stats, f'slave{i}.lag')
        if slave_offset != get(info_stats, 'master_repl_offset'):
            slave_offset = _color(slave_offset)
        if slave_lag > 1:
            slave_lag = _color(slave_lag)
        metrics += [
            {
                'category': 'REPLICA',
                'metric': f"slave{i}.offset",
                'desc': f"Offset (Slave {i})",
                'value': slave_offset,
            },
            {
                'category': 'REPLICA',
                'metric': f"slave{i}.lag",
                'desc': f"Lag from last slave{i} replconf ack (every 1s)",
                'value': slave_lag,
            },
        ]

    cluster_enabled = get(info_stats, 'cluster_enabled', -1) == 1
    metrics += [
        {
            'category': 'CLUSTER',
            'metric': "cluster_enabled",
            'desc': "In cluster mode",
            'value': cluster_enabled,
        },
    ]
    if cluster_enabled:
        metrics += _get_cluster_metrics(host, port, password)
    pretty_print(sorted(metrics, key=lambda m: m['category']), mappings={
        'Category': 'category',
        'Metric': 'metric',
        'Description': 'desc',
        'Value': 'value',
    }, x=x)


@cli.command(help='Give an idea about load')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('--password')
def load_info(host, port, password):
    r = redis.StrictRedis(host=host, port=port, password=password)
    result = [{'cmd': k.split('_')[1], "usec_per_call": int(v['usec_per_call'])} for k, v in r.info('commandstats').items()][:20]
    result = sorted(result, key=lambda s: s['usec_per_call'], reverse=True)
    for item in result:
        if item['usec_per_call'] > 100:
            item['usec_per_call'] = _color(item['usec_per_call'])
    pretty_print(result, mappings={'Command': 'cmd', 'Average usec': 'usec_per_call'})
    print('-----')
    print('(Try `redis-cli -stat` to monitor load live)')

@cli.command(help='Scan bigkeys')
def bigkeys():
    print("Enough to use native cli: redis-cli --bigkeys")


@cli.command(help='Set configs')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('--slowlog-log-slower-than', default=10000, type=int, help='In microsecond (us)', show_default=True)
@click.option('--slowlog-max-len', default=100, type=int, help='Length of an in-memory list to hold slowlog', show_default=True)
@click.option('--rewrite', '-w', is_flag=True)
def customize_configs(
        host, port,
        slowlog_log_slower_than,
        slowlog_max_len,
        rewrite,
):
    r = redis.Redis(host=host, port=port, db=0)
    r.config_set('slowlog-log-slower-than', slowlog_log_slower_than)
    r.config_set('slowlog-max-len', slowlog_max_len)

    r.config_set('client-output-buffer-limit', 'normal 20mb 10mb 120')
    if rewrite:
        r.config_rewrite()
    pass

@cli.command(help='Tuning Linux')
def os_tuning():
    print('\n'.join([
        'sysctl -w vm.overcommit_memory=1 >> /etc/sysctl.conf',
        'sysctl -w vm.swapniess=1 >> /etc/sysctl.conf',
        'echo never > /sys/kernel/mm/transparent_hugepage/enabled',
        'echo "echo never > /sys/kernel/mm/transparent_hugepage/enabled" >>/etc/rc.local',
        'sysctl -w net.core.somaxconn=4096 >> /etc/sysctl.conf',
    ]))

@cli.command(help='Show slowlog')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('--slower-than', '-lt', default=1000, type=int, show_default=True)
@click.option('--sort', is_flag=True)
def slowlog(host, port, slower_than, sort):
    r = redis.StrictRedis(host=host, port=port, db=0)
    result = r.slowlog_get()
    if sort:
        result.sort(key=lambda item: item['duration'], reverse=True)
    result = filter(lambda item: item['duration'] >= slower_than, result)
    pretty_print(result, mappings={
        'ID': 'id',
        'Start': ('start_time', lambda ts: datetime.datetime.fromtimestamp(ts)),
        'Duration': ('duration', lambda d: f'{d // 1000}ms,{d % 1000}us'),
        'Command': ('command', lambda c: c.decode('utf-8'))
    })
    print(f'(total: {r.slowlog_len()})')


@cli.command(help='Test memory')
@click.option('--size', '-s', default=1024, type=int, help='The amount of mem (in MB) to occupy for testing', show_default=True)
def occupy_mem(size):
    print(f"redis-server --test-memory {size}")


@cli.command(help='Subscribe')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('--channel', '-c', default='*', show_default=True)
def sub(host, port, channel):
    r = redis.StrictRedis(host=host, port=port, client_name='corgi-sub')
    s = r.pubsub()
    s.psubscribe(channel)
    for item in s.listen():
        print(item)


@cli.command(help='Publish')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('--channel', '-c', default='channel:test', show_default=True)
@click.option('--body', '-b', default='test', show_default=True)
def pub(host, port, channel, body):
    r = redis.StrictRedis(host=host, port=port)
    r.publish(channel, body)


def _type(flags):
    result = []
    if 'A' in flags:
        result += ['Closing']
    elif 'b' in flags:
        result += ['Blocking']
    elif 'c' in flags:
        result += ['Closing(w)']
    elif 'd' in flags:
        result += ['EXEC Failed']
    elif 'i' in flags:
        result += ['I/O Waiting']
    elif 'M' in flags:
        result += ['Master']
    elif 'O' in flags:
        result += ['Monitor']
    elif 'P' in flags:
        result += ['Pub/Sub']
    elif 'r' in flags:
        result += ['RO']
    elif 'S' in flags:
        result += ['Replica node']
    elif 'u' in flags:
        result += ['Unblocked']
    elif 'U' in flags:
        result += ['Unix']
    elif 'x' in flags:
        result += ['MULTI/EXEC']
    elif 't' in flags:
        result += ['Tracking']
    elif 'R' in flags:
        result += ['Invalid Tracking']
    elif 'B' in flags:
        result += ['Broadcast Tracking']
    return ','.join(result) if result else ''


@cli.command(help='Show clients info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
@click.option('-x', is_flag=True)
def clients(host, port, x):
    '''https://redis.io/commands/client-list/'''
    r = redis.StrictRedis(host=host, port=port, client_name='corgi')
    pretty_print(r.client_list(), mappings={
        'ID': 'id',
        # 'Addr': 'addr',
        'Name': 'name',
        'Type': ('flags', lambda flags: _type(flags)),
        'Age': ('age', lambda age: pretty_duration(age)),
        'Idle': ('idle', lambda idle: pretty_duration(idle)),
        # 'External': ('fd', lambda fd: fd != -1),  # if fd == -1, means it is an internal client used in redis server
        # if qbuf > 1GB, client will be closed, in bytes
        'I-Q (mem)': ('qbuf', lambda b: b if int(b) < 1024 * 1024 else click.style(b, fg='red', bold=True)),
        # output queue mem consumption, in bytes
        'O-Q (mem)': 'omem',
        'O-Q (size)': ('oll', lambda l: l if int(l) < 32 else _color(l)),
        'CMD': 'cmd'
    }, x=x)


def main():
    config_logging('corgi_redis')
    cli()


if __name__ == '__main__':
    main()
