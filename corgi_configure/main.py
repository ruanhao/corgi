#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging, run_script, is_root, bye, as_root, switch_cwd
from corgi_common.scriptutils import run_script_as_root_live
import json
import tempfile
import logging
from . import k8s

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

config_logging('corgi_configure', logging.DEBUG)

def _register_commands(module):
    for a in dir(module):
        f = getattr(module, a)
        if isinstance(f, click.core.Command):
            cli.add_command(f)

@as_root
def run_as_root(*args, **kwargs):
    run_script(*args, **kwargs)

@click.group(help="Handy scripts", context_settings=CONTEXT_SETTINGS)
@click.pass_context
def cli(ctx):
    pass

@cli.command()
@click.option('--dry', is_flag=True)
@click.option('--root-dir', '-d', default='/srv/tftp', help='root directory', show_default=True)
@click.option('--port', '-p', default=69, type=int, show_default=True)
def tftp_server(dry, root_dir, port):
    script = f"""sudo apt-get install tftpd-hpa -y
cat <<EOF | sudo tee /etc/default/tftpd-hpa
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="{root_dir}"
TFTP_ADDRESS=":{port}"
TFTP_OPTIONS="--secure --create"
EOF
sudo chmod 777 {root_dir}
sudo mkdir -p {root_dir}
sudo systemctl restart tftpd-hpa.service
"""
    run_script_as_root_live(script, dry=dry)
    pass

@cli.command(short_help="Enable/Disable offload by ethtool")
@click.option('--dry', is_flag=True)
@click.option('--on', is_flag=True, help='Enable offload')
@click.option('--off', is_flag=True, help='Disable offload')
@click.option('--device', '-d', default='eth0', help='Device name')
@click.option('--dump', is_flag=True, help='Dump offload status')
def offload(dry, on, off, device, dump):
    """
https://www.linuxquestions.org/questions/linux-networking-3/help-needed-disabling-tcp-udp-checksum-offloading-in-debian-880233/
https://michael.mulqueen.me.uk/2018/08/disable-offloading-netplan-ubuntu/
    """
    if on and off:
        bye("Cannot enable and disable at the same time")
    if not on and not off:
        bye("Should specify either on or off")
    switch = "on" if on else "off"
    script = f"""which ethtool || sudo apt install ethtool -y
sudo ethtool --offload {device} rx {switch} tx {switch}
sudo ethtool -K {device} gso {switch} gro {switch}"""
    if dump:
        script += f"sudo ethtool --show-offload {device}"
    run_script_as_root_live(script, dry=dry)


@cli.command()
@click.option('--device', '-d', required=True, help='Specify block device')
@click.option('--mountpoint', '-m', required=True)
@click.option('--filesystem', '-fs', default='ext4', show_default=True)
@click.option('--dry', is_flag=True)
def mkfs_and_mount(dry, device, mountpoint, filesystem):
    script = f'''mkfs -t {filesystem} {device}
mkdir -p {mountpoint}
mount {device} {mountpoint}
'''
    run_script_as_root_live(script, dry=dry)

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


@cli.command(short_help="Generate KUBECONFIG for user")
@click.option("--api-server", '-s', help='API Server address', required=True)
@click.option("--api-server-port", default=6443, help='API Server port')
@click.option("--pki-path", default='/etc/kubernetes/pki', help="Directory where CA resides")
@click.option("--cfssl-version", default='1.6.1', help="CFSSL version")
@click.option("--user", '-u', required=True)
@click.option("--group", '-g', required=True)
@click.option("--namespace", '-ns', default='default')
@click.option('--dry', is_flag=True)
@click.option('--userspace', is_flag=True, help='Namespace based or cluster based access level')
@click.option("--expiry-days", '-e', default=3650, help='Expiry days for certificate')
def k8s_user_conf(api_server, api_server_port, pki_path, dry, cfssl_version, user, group, expiry_days, namespace, userspace):
    '''Generate KUBECONFIG file which can be used to authenticate/authorize user with default cluster-admin role'''
    api_server = f"https://{api_server}:{api_server_port}"
    cfssl_url = f"https://github.com/cloudflare/cfssl/releases/download/v{cfssl_version}/cfssl_{cfssl_version}_linux_amd64"
    cfssljson_url = f"https://github.com/cloudflare/cfssl/releases/download/v{cfssl_version}/cfssljson_{cfssl_version}_linux_amd64"
    cfssl_certinfo_url = f"https://github.com/cloudflare/cfssl/releases/download/v{cfssl_version}/cfssl-certinfo_{cfssl_version}_linux_amd64"

    req = {
        'CN': user,
        'hosts': [],
        'key': {
            'algo': 'rsa',
            'size': 2048
        },
        'names': [{'O': group}]

    }

    ca_config = {
        "signing": {
            "default": {
                "expiry": "87600h"
            },
            "profiles": {
                "kubernetes": {
                    "expiry": f"{expiry_days * 24}h",
                    "usages": [
                        "signing",
                        "key encipherment",
                        "server auth",
                        "client auth"
                    ]
                }
            }
        }
    }

    script = f'''set -e
if ! which cfssl; then
    wget {cfssl_url} -O /usr/local/bin/cfssl
    wget {cfssljson_url} -O /usr/local/bin/cfssljson
    wget {cfssl_certinfo_url} -O /usr/local/bin/cfssl-certinfo
    chmod a+x /usr/local/bin/cfssl*
fi
# Generate certificate
echo '{json.dumps(ca_config)}' > ca-config.json
echo '{json.dumps(req)}' | cfssl gencert -config=ca-config.json -ca={pki_path}/ca.crt -ca-key={pki_path}/ca.key -profile=kubernetes - | cfssljson -bare {user}

# Setup conf file
kubectl config set-cluster kubernetes \\
    --certificate-authority={pki_path}/ca.crt \\
    --embed-certs=true \\
    --server={api_server} \\
    --kubeconfig={user}.conf # output conf
kubectl config set-credentials {user} \\
    --client-certificate={user}.pem \\
    --client-key={user}-key.pem \\
    --embed-certs=true \\
    --kubeconfig={user}.conf
kubectl config set-context kubernetes \\
    --cluster=kubernetes \\
    --user={user} \\
    --namespace={namespace} \\
    --kubeconfig={user}.conf
kubectl config use-context kubernetes --kubeconfig={user}.conf
&>/dev/null kubectl create namespace {namespace} || true
&>/dev/null kubectl delete rolebinding {user}-admin-binding || true
&>/dev/null kubectl delete clusterrolebinding {user}-admin-binding || true
kubectl create {"rolebinding" if userspace else "clusterrolebinding"} {user}-admin-binding --clusterrole=cluster-admin --user={user} --namespace={namespace} # --namespace is only useful for rolebinding
echo
'''
    if dry:
        print(script)
        return
    tmp_dir = tempfile.mkdtemp()
    with switch_cwd(tmp_dir):
        run_as_root(script, realtime=True)
        click.echo(f'Done. Please check by running: KUBECONFIG={tmp_dir}/{user}.conf kubectl get all')


@cli.command(short_help="Create a Swap File on Linux with dd Command")
@click.option('--size', '-s', 'size_k', default=1024, type=int, help='Size of swap file in MB')
@click.option('--swapfile', default='/swapfile', help='Swap file path')
@click.pass_context
def swapfile(ctx, size_k, swapfile):
    count = size_k * 1024
    script = f'''
if [ -f {swapfile} ]; then
    echo "Swap file already exists: {swapfile}"
    exit 1
fi
sudo dd if=/dev/zero of={swapfile} bs=1024 count={count}
sudo mkswap {swapfile} && sudo chmod 0600 {swapfile}
sudo swapon {swapfile}
echo "{swapfile} none swap sw 0 0" | sudo tee -a /etc/fstab'''
    click.echo(script)


_register_commands(k8s)
