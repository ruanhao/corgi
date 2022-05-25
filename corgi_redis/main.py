#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging, pretty_print
from corgi_common.dateutils import pretty_duration
import redis
import datetime
from pprint import pprint

def _color(text):
    return click.style(f'{text}', fg='red')

@click.group(help="CLI tool for Redis")
def cli():
    pass

@cli.command(help='Show redis usage info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=6379, type=int, show_default=True)
def info(host, port):
    r = redis.Redis(host=host, port=port, db=0)
    dbsize = r.dbsize()
    info_stats = r.info()
    # pprint(info_stats)
    rejected_connections = info_stats['rejected_connections']
    if rejected_connections > 0:
        rejected_connections = click.style(f'{rejected_connections}', fg='red')
    if int(info_stats['used_memory']) / int(info_stats['maxmemory']) > 0.8:
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
    pretty_print([
        {'metric': 'redis_version', 'value': info_stats['redis_version'], 'desc': 'Version', 'category': 'BASIC'},
        {'metric': 'redis_mode', 'value': info_stats['redis_mode'], 'desc': 'Running mode', 'category': 'BASIC'},
        {'metric': 'uptime_in_seconds', 'value': pretty_duration(info_stats['uptime_in_seconds']), 'desc': 'Uptime', 'category': 'BASIC'},

        {'metric': 'used_memory_human', 'value': info_stats['used_memory_human'], 'desc': 'Mem', 'category': 'Memory'},
        {'metric': 'used_memory_peak_human', 'value': info_stats['used_memory_peak_human'], 'desc': 'Mem Peak', 'category': 'Memory'},
        {'metric': 'used_memory_rss_human', 'value': info_stats['used_memory_rss_human'], 'desc': 'RSS', 'category': 'Memory'},
        {'metric': 'maxmemory_human', 'value': info_stats['maxmemory_human'], 'desc': 'Max memory allowed', 'category': 'Memory'},
        {'metric': 'maxmemory_policy', 'value': info_stats['maxmemory_policy'], 'desc': 'Max memory Policy', 'category': 'Memory'},

        {'metric': 'total_connections_received', 'value': info_stats['total_connections_received'], 'desc': 'Total connections ever', 'category': 'TCP'},
        {'metric': 'rejected_connections', 'value': info_stats['rejected_connections'], 'desc': 'Ever rejected connections', 'category': 'TCP'},

        {'metric': 'dbsize', 'value': dbsize, 'desc': 'Total size of keys', 'category': 'DATA'},

        {'metric': 'rdb_last_save_time', 'value': datetime.datetime.fromtimestamp(int(info_stats['rdb_last_save_time'])), 'desc': 'Last time of saving snapshot', 'category': 'RDB'},
        {'metric': 'rdb_last_bgsave_status', 'value': info_stats['rdb_last_bgsave_status'], 'desc': 'Last saving snapshot status', 'category': 'RDB'},
        {'metric': 'rdb_last_bgsave_time_sec', 'value': info_stats['rdb_last_bgsave_time_sec'], 'desc': 'Time consumption of last saving snapshot', 'category': 'RDB'},
        {'metric': 'latest_fork_usec', 'value': info_stats['latest_fork_usec'], 'desc': 'Time consumption of last fork', 'category': 'RDB/AOF'},

        {'metric': 'aof_enabled', 'value': info_stats['aof_enabled'] == 1, 'desc': 'AOF enabled', 'category': 'RDB'},
        {'metric': 'aof_last_bgrewrite_status', 'value': info_stats['aof_last_bgrewrite_status'], 'desc': 'Last AOF status', 'category': 'RDB'},
        {'metric': 'aof_delayed_fsync', 'value': info_stats.get('aof_delayed_fsync', -1), 'desc': 'fsync consumed >2s time', 'category': 'RDB'},

    ], mappings={
        'Category': 'category',
        'Metric': 'metric',
        'Description': 'desc',
        'Value': 'value',
    })


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
