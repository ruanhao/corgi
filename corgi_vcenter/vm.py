import click
import logging
import datetime
from .vmagent import Agent as VmAgent
from .folderagent import Agent as FolderAgent
from corgi_common import tabulate_print, run_script
import json
import os
import tempfile
import subprocess

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@click.group(help="Utils for VM management")
@click.pass_context
def vm(ctx):
    pass


@click.command(help="List VM")
@click.option('--on', is_flag=True, default=None, help="List only PowerOn VM")
@click.option('--hosts', required=False, help="List only VM on the host")
@click.option('--folder-names', '-f', required=False, help="List only VM under the folder names")
@click.pass_context
def list_vm(ctx, on, hosts, folder_names):
    agent = VmAgent.getAgent(**ctx.obj)
    folder_ids = []
    if folder_names:
        r = FolderAgent.getAgent(**ctx.obj).list_folders(names=folder_names)
        if r.ok:
            folder_ids.extend(f['folder'] for f in r.json()['value'])
    if folder_ids:
        folder_ids = ",".join(list(set(folder_ids)))
    elif folder_names:          # specify folder name explicitly
        folder_ids = 'unknown'
    r = agent.list_vms(
        power_states='POWERED_ON' if on else None,
        hosts=hosts,
        folder_ids=folder_ids,
    )
    assert r.ok, r.text
    data = r.json()['value']
    data = sorted(data, key=lambda v: v['power_state'], reverse=True)
    tabulate_print(data, {
        'vm': 'vm',
        'Mem': 'memory_size_MiB',
        'Power': 'power_state',
        'CPU': 'cpu_count',
        'Name': 'name',
    })


@click.command(help="Show VM info")
@click.argument('vm', required=True)
@click.pass_context
def show_vm(ctx, vm):
    agent = VmAgent.getAgent(**ctx.obj)
    r = agent.show_vm(vm)
    assert r.ok, r.text
    data = r.json()['value']
    print(json.dumps(data, indent=4))


@click.command(help="Delete VM")
@click.argument('vm', required=True)
@click.pass_context
def delete(ctx, vm):
    agent = VmAgent.getAgent(**ctx.obj)
    agent.poweroff(vm)
    r = agent.delete_vm(vm)
    assert r.ok, r.text


@click.command(help="Show VM info")
@click.option('--ova-path', '-p', required=True, help="OVA path")
@click.option('--spec-path', '-sp', required=False, help="Spec json file path")
@click.option('--resource-pool', '-r', default='*/Resources', help="Resource pool (govc find . -type p)", envvar='GOVC_RESOURCE_POOL')
@click.option('--datastore', '-s', required=True, help="Datastore (govc find . -type s)", envvar='GOVC_DATASTORE')
@click.option('--folder', '-f', required=False, help="Folder (govc find . -type f)", envvar='GOVC_FOLDER')
@click.option('--cpu', required=False, default=4, help="CPU number")
@click.option('--mem', required=False, default=8192, help="Memory (MB)")
@click.option('--dry', is_flag=True)
@click.option('--name', '-n', required=False, help="VM name")
@click.option('--poweron/--no-poweron', default=True)
@click.pass_context
def deploy_ova(ctx, ova_path, datastore, resource_pool, folder, spec_path, cpu, mem, dry, name, poweron):
    logger.info(f"ova_path: {ova_path}, rp: {resource_pool}, ds: {datastore}, folder: {folder}")
    filename = ova_path.split('/')[-1].replace('.ova', '')
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    vm_name = f'{name or filename}-haoru-{timestamp}'[:80]
    if not spec_path:
        spec = {
            "DiskProvisioning": "flat",
            "IPAllocationPolicy": "dhcpPolicy",
            "IPProtocol": "IPv4",
            "NetworkMapping": [
                {"Name": "VM Network", "Network": "Subnet113"}
            ],
            "MarkAsTemplate": False,
            "PowerOn": False,
            "InjectOvfEnv": False,
            "WaitForIP": False,
            "Name": None
        }
        spec_path = os.path.join(tempfile.gettempdir(), 'spec.json')
        with open(spec_path, 'w') as f:
            f.write(json.dumps(spec, indent=4))
    default_folder = "/" + datastore.split('/')[1] + "/vm"
    cmd = f"""export GOVC_INSECURE=1
export GOVC_URL={ctx.obj['url']}
export GOVC_USERNAME={ctx.obj['username']}
export GOVC_FOLDER={folder if folder else ''}
export GOVC_PASSWORD={ctx.obj['password']}
export GOVC_DATASTORE={datastore}
export GOVC_RESOURCE_POOL={resource_pool}
govc import.ova -options={spec_path} --name={vm_name} {ova_path} && \\
govc vm.change -debug -vm {(folder if folder else default_folder) + "/" + vm_name} -c {cpu} -m {mem} && \\
govc vm.power  -{"on" if poweron else "off"} {(folder if folder else default_folder) + "/" + vm_name}
"""
    if dry:
        click.echo(cmd)
    else:
        run_script(cmd, realtime=True)


vm.add_command(list_vm, "list")
vm.add_command(show_vm, "info")
vm.add_command(deploy_ova)
vm.add_command(delete)
