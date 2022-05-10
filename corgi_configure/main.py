#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging, run_script, is_root, bye
import logging

config_logging('corgi_misc', logging.DEBUG)

@click.group(help="Handy scripts")
def cli():
    pass

@cli.command()
@click.option('--dry', is_flag=True)
@click.option('--dir', '-d', "dir_", default='/nfsdata', help='The directory to share')
def ubuntu_nfs_server(dry, dir_):
    script = f"""apt update && apt install nfs-kernel-server -y
mkdir {dir_}
chmod 777 {dir_}
chown nobody:nogroup {dir_}
echo "{dir_} *(rw,no_root_squash,no_all_squash,sync,no_subtree_check)" >> /etc/exports
# exportfs -ra
systemctl restart nfs-kernel-server
"""
    if dry:
        print(script)
        return
    if not is_root():
        bye("Should run as root.")
    run_script(script, realtime=True)

@cli.command()
@click.option("--server", '-s', help="Server address")
@click.option("--server-dir", '-sd', default='/nfsdata', help="Server sharing directory")
@click.option("--local-dir", '-ld', default='/mnt/nfsdata', help="Local mounting directory")
@click.option('--dry', is_flag=True)
def ubuntu_nfs_client(server, server_dir, local_dir, dry):
    script = f"""apt update && apt install nfs-common -y
showmount -e {server} # just for check
mkdir -p {local_dir}
mount {server}:{server_dir} {local_dir}
echo "{server}:{server_dir} {local_dir} nfs rw,hard,intr,rsize=8192,wsize=8192,timeo=14 0 0" >>/etc/fstab
"""
    if dry:
        print(script)
        return
    if not is_root():
        bye("Should run as root.")
    run_script(script, realtime=True)
