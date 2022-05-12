import click
from corgi_common import run_script, bye, as_root, switch_cwd, _chain_get, assert_that
import os
import json
from string import Template
import tempfile

@as_root
def _run_as_root(*args, **kwargs):
    run_script(*args, **kwargs)


def _get_script(name, values={}):
    filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sh', name)
    with open(filepath, 'r') as f:
        return Template(f.read()).safe_substitute(values)


@click.command(short_help="Bootstrap master node")
@click.option("--kubernetes-version", default='1.23.6')
@click.option("--pod-network", default='192.168.0.0/16')
@click.option("--helm-version", default='3.8.2')
@click.option("--metrics-server-version", default='0.6.1')
@click.option("--dry", is_flag=True)
def k8s_bootstrap_master(dry, **values):
    common_script = _get_script('k8s_bootstrap_common.sh', values)
    master_script = _get_script('k8s_bootstrap_master.sh', values)
    script = common_script + "\n" + master_script
    if dry:
        print(script)
        return
    _run_as_root(script, realtime=True, opts='e')


@click.command(short_help="Bootstrap worker node")
@click.option("--kubernetes-version", default='1.23.6')
@click.option("--ip", "master_ip", required=True, help='Master node global IP address')
@click.option("--dry", is_flag=True)
def k8s_bootstrap_worker(dry, **values):
    common_script = _get_script('k8s_bootstrap_common.sh', values)
    master_script = _get_script('k8s_bootstrap_worker.sh', values)
    script = common_script + "\n" + master_script
    if dry:
        print(script)
        return
    _run_as_root(script, realtime=True, opts='e')


@click.command(short_help="Deploy glusterfs")
@click.option("--dry", is_flag=True)
@click.option("--device", '-d', default='/dev/sdb', help='Block device used for storage on node')
@click.option("--key", '-k', default='Th15I5MyK3y', help='Restful API key for glusterfs')
def k8s_deploy_glusterfs(dry, device, **values):
    rc, stdout, stderr = run_script("kubectl get node -o json", capture=True)
    assert_that(rc == 0, stderr)
    nodes = json.loads(stdout)['items']
    assert_that(len(nodes) >= 3, "Need a minimum of three storage nodes.")
    hostname_ip_mappings = []
    for node in nodes:
        name = _chain_get(node, 'metadata.name')
        assert_that(name, "No name(hostname) found for node")
        addresses = _chain_get(node, 'status.addresses')
        assert_that(addresses, "No addresses(ip) found for node")
        ip = list(filter(lambda addr: addr['type'] == 'InternalIP', addresses))[0]['address']
        hostname_ip_mappings.append((name, ip))
    nodes_desc = []
    for hostname, ip in hostname_ip_mappings:
        nodes_desc.append({
            "node": {
                "hostnames": {
                    "manage": [hostname],
                    "storage": [ip]
                },
                "zone": 1
            },
            "devices": device.split(',')
        })
    topology = {'clusters': [{'nodes': nodes_desc}]}
    script = _get_script('k8s-install-glusterfs.sh', {**values, 'topology': json.dumps(topology, indent=4), 'tmp_dir': tempfile.mkdtemp()})
    if dry:
        print(script)
        return
    _run_as_root(script, realtime=True)
