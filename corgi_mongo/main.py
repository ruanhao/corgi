#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import time
import json
from corgi_common import config_logging, pretty_print, get, bye
from corgi_common.dateutils import pretty_duration
import logging
import pymongo
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

def _mongo_client(host, port):
    mongo_client = pymongo.MongoClient(host, port)
    try:
        mongo_client.server_info()
    except Exception as ex:
        bye(f"Failed to connect to MongoDB: {ex}")
    return mongo_client

def _mongo_db(host, port, db):
    return _mongo_client(host, port)[db]

def _mongo_collection(host, port, db, collection):
    return _mongo_db(host, port, db)[collection]


@click.group(help="CLI tool for MongoDB")
def cli():
    pass


def _compress(doc, k):
    return str(doc[k]).replace(' ', '')[:128]

def _compress0(doc, length=100):
    if not doc:
        return 'n/a'
    return str(doc).replace(' ', '')[:length]

def _print_profiles(docs, brief=False, offset=0):
    if not brief:
        for idx, doc in enumerate(docs, 1 + offset):
            s = f"--- [ Record {idx} ] ---\n{json.dumps(doc, indent=2, default=str)}"
            logger.info(s)
            print(s)
        return

    # for doc in docs:
    #     op = doc['op']
    #     if op == 'query':
    #         doc['stmt'] = _compress(doc, 'query')
    #     elif op == 'update':
    mappings = {
        'ts': 'ts',
        'op': 'op',
        'app': 'appName',
        'coll': ('ns', lambda ns: ns.split('.')[-1]),
        'millis': ('millis', lambda m: _color(m, lambda v: v > 100)),
        'q': ('query', _compress0),
        'u': ('updateobj', _compress0),
        'command': ('command', _compress0),
        'nMatched': 'nMatched',
        'nModified': 'nModified',
    }
    for idx, doc in enumerate(docs, 1 + offset):
        logger.info(f"--- [ Record {idx} ] ---\n{json.dumps(doc, indent=2, default=str)}")
    pretty_print(docs, mappings=mappings, x=True, offset=offset)

@cli.command(help='Show memory info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=27017, type=int, show_default=True)
def mem_info(host, port):
    db = _mongo_db(host, port, 'admin')
    server_status = db.command('serverStatus')
    print(get(server_status, 'tcmalloc.tcmalloc.formattedString'))

@cli.command(help='Show DB info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=27017, type=int, show_default=True)
@click.option('--port', '-p', default=27017, type=int, show_default=True)
@click.option('--db', "dbname", required=True)
def db_info(host, port, dbname):
    db = _mongo_db(host, port, dbname)
    j = db.command('dbStats', scale=1024 * 1024)
    for n in ['ok', 'db', 'scaleFactor']:
        if n in j:
            del j[n]
    for k, v in j.items():
        if k == 'collections':
            info(f"{k:15s}: {v:11d} (Number of collections)")
        elif k == 'views':
            info(f"{k:15s}: {v:11d} (Number of views)")
        elif k == 'objects':
            info(f"{k:15s}: {v:11d} (Number of documents)")
        elif k == 'avgObjSize':
            info(f"{k:15s}: {v/1024:10.2f}K (Average size of each document)")
        elif k == 'indexes':
            info(f"{k:15s}: {v:11d} (Number of indexes)")
        elif k == 'indexSize':
            info(f"{k:15s}: {v:10.2f}M (Sum of the space allocated to all indexes)")
        elif k == 'dataSize':
            info(f"{k:15s}: {v:10.2f}M (Total size of the uncompressed data)")
        elif k == 'storageSize':
            info(f"{k:15s}: {v:10.2f}M (Sum of the space allocated for db)")
        elif k == 'totalSize':
            info(f"{k:15s}: {v:10.2f}M (Sum of index size and storage size)")
        elif k == 'fsUsedSize':
            info(f"{k:15s}: {v/1024:10.2f}G (OS disk space in use)")
        elif k == 'fsTotalSize':
            info(f"{k:15s}: {v/1024:10.2f}G (OS all disk capacity)")
        else:
            info(f"{k:15s}: {v:11}")
    pass

@cli.command(help='Show basic info')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=27017, type=int, show_default=True)
def basic_info(host, port):
    db = _mongo_db(host, port, 'admin')
    build_info = db.command('buildInfo')
    host_info = db.command('hostInfo')
    server_status = db.command('serverStatus')

    comm_status = db.command('getCmdLineOpts')

    res = {}

    res['db_path'] = get(comm_status, 'parsed.storage.dbPath')
    res['cache_size'] = get(comm_status, 'parsed.storage.wiredTiger.engineConfig.cacheSizeGB')
    res['log_file'] = get(comm_status, 'parsed.systemLog.path')

    res['mongo_version'] = get(build_info, 'version')
    res['os_cpu_freq'] = get(host_info, 'extra.cpuFrequencyMHz')
    res['os_kernel_version'] = get(host_info, 'extra.kernelVersion')
    _os = get(host_info, 'os')
    res['os'] = f"{_os['name']}({_os['version']})"
    res['os_mem'] = get(host_info, 'system.memSizeMB')
    res['os_cpu_cores'] = get(host_info, 'system.numCores')
    res['os_cpu_arch'] = get(host_info, 'system.cpuArch')

    res['conns'] = get(server_status, 'connections.current')
    res['uptime'] = get(server_status, 'uptime')
    res['bytes_in'] = get(server_status, 'network.bytesIn')
    res['bytes_out'] = get(server_status, 'network.bytesOut')

    pretty_print([res], mappings={
        'Version': 'mongo_version',
        'Kernel': 'os_kernel_version',
        'OS': 'os',
        'CPU Frequency (MHZ)': 'os_cpu_freq',
        'OS Mem': 'os_mem',
        'OS CPUs': 'os_cpu_cores',
        'OS Arch': 'os_cpu_arch',
        'Connections': 'conns',
        'Uptime': ('uptime', pretty_duration),
        'DB path': 'db_path',
        'Cache Size (GB)': 'cache_size',
        'Log file': 'log_file',
        # 'Bytes in (KB)': ('bytes_in', lambda x: int(x / 1024)),
        # 'Bytes out (KB)': ('bytes_out', lambda x: int(x / 1024)),
    }, x=True, header=False)


@cli.command(help='Profiling')
@click.option('--host', '-h', default='localhost', show_default=True)
@click.option('--port', '-p', default=27017, type=int, show_default=True)
@click.option('--op', default=None, type=click.Choice([
    'command',
    'count',
    'distinct',
    'geoNear',
    'getMore',
    'group',
    'insert',
    'mapReduce',
    'query',
    'remove',
    'update',
    '',
]), show_default=True)
@click.option('--db', "dbname", required=True)
@click.option('--app', help='Filter by appName')
@click.option('--collection', '-c', help='Filter by collection')
@click.option('--brief', '-b', is_flag=True)
@click.option('--slowms', type=int)
def profile(host, port, dbname, op, brief, app, collection, slowms):
    limit = 64
    fetched_ts = set()

    db = _mongo_db(host, port, dbname)
    system = db['system']
    _filter = {'ns': {"$ne": f'{dbname}.system.profile'}}
    if slowms is not None:
        _filter['millis'] = {'$gt': slowms}
    if op:
        _filter['op'] = op
    if collection:
        _filter['ns'] = f'{dbname}.{collection}'
    if app:
        _filter['appName'] = app

    for doc in system.profile.find(_filter).limit(limit).sort('ts', -1):
        fetched_ts.add(doc['ts'])

    if slowms is not None:
        logger.info(f"Set profile level to 1 with slowms={slowms}")
        db.command("profile", 1, slowms=slowms)
    else:
        logger.info(f"Set profile level to 2 with filter: {_filter}")
        db.command("profile", 2, filter=_filter)
    offset = 0
    try:
        while True:
            docs = system.profile.find(_filter).limit(limit).sort('ts', -1)
            new_docs = []
            for doc in docs:
                ts = doc['ts']
                if ts not in fetched_ts:
                    fetched_ts.add(ts)
                    new_docs += [doc]
            if new_docs:
                _print_profiles(new_docs, brief, offset=offset)
                offset += len(new_docs)
            time.sleep(1)
    finally:
        logger.info("Set profile level back to 0")
        db.command("profile", 0)
    pass

def main():
    config_logging('corgi_mongo')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
