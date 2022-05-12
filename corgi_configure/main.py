#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
from corgi_common import config_logging, run_script, is_root, bye, as_root, switch_cwd
import json
import tempfile
import logging
from . import k8s

config_logging('corgi_configure', logging.DEBUG)

def _register_commands(module):
    for a in dir(module):
        f = getattr(module, a)
        if isinstance(f, click.core.Command):
            cli.add_command(f)

@as_root
def run_as_root(*args, **kwargs):
    run_script(*args, **kwargs)

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


_register_commands(k8s)
