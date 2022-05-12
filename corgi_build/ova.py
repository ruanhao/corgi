import click
import logging
import os
import shutil
from string import Template
from corgi_common import run_script, switch_cwd

logger = logging.getLogger(__name__)
dir_path = os.path.dirname(os.path.realpath(__file__))

def fatal(msg):
    logger.critical(msg)
    click.echo(msg, err=True)
    raise click.Abort()


def info(msg):
    logger.info(msg)
    click.echo(msg)


@click.group(help="Utils for building OVA")
def ova():
    pass


def _prepare_preseed_cfg(username, password, swapsize, os_code):
    logger.info("Creating common preseed config ...")
    rendered = ''
    with open(os.path.join(dir_path, 'preseed.cfg.template'), 'r') as f:
        tplt = Template(f.read())
        rendered = tplt.substitute({
            'SWAP_SIZE': swapsize,
            'username': username,
            'password': password
        })
    os.makedirs(os.path.join('http', 'ubuntu'))
    with open(os.path.join('http', 'ubuntu', 'preseed.cfg'), 'w') as f:
        f.write(rendered)

    logger.info(f"Creating preseed config for {os_code} ...")
    rendered = ''
    with open(os.path.join(dir_path, f'preseed-{os_code}.cfg.template'), 'r') as f:
        tplt = Template(f.read())
        rendered = tplt.substitute({
            'username': username,
        })
    os.makedirs(os.path.join('http', f'ubuntu-{os_code}'))
    with open(os.path.join('http', f'ubuntu-{os_code}', 'preseed.cfg'), 'w') as f:
        f.write(rendered)


def _prepare_ovf(name, os_code, memory, cpu, disk, version):
    logger.info("Creating ovf file ...")
    rendered = ''
    with open(os.path.join(dir_path, 'ubuntu.ovf.template'), 'r') as f:
        tplt = Template(f.read())
        rendered = tplt.substitute({
            'cpu': cpu,
            'memory': memory,
            'disk': disk,
            'version': version,
            'name': name,
            'os_code': os_code
        })
    with open('ubuntu.ovf', 'w') as f:
        f.write(rendered)


@click.command(help="Build Ubuntu")
@click.option('--cpu', '-c', default=4, help="CPU count")
@click.option('--memory', '-m', default=1024, type=int, help="Memory (MB)")
@click.option('--disk', '-d', default=80, type=int, help="Disk size (GB)")
@click.option('--swap', type=int, help="Swap size (MB)")
@click.option('--os', "os_code", default='focal', type=click.Choice(['focal']), help="OS code")
@click.option('--name', help="OVA filename")
@click.option('--version', default='1.0.0', help="Version")
@click.option('--username', default='cisco', help="Login username")
@click.option('--password', default='cisco', help="Login password")
@click.option('--dry', is_flag=True, help="Show script without running")
@click.option('--no-swap', is_flag=True, help="Disable swap")
def ubuntu(cpu, memory, disk, swap, os_code, name, version, username, password, dry, no_swap):
    if not swap:
        swap = int(memory / 2)
    if not name:
        name = "my-ubuntu"
    if not version.startswith('v'):
        version = 'v' + version
    disk *= 1024
    logger.info(f"Starting building ova, cpu: {cpu}, memory: {memory}, disk: {disk}, swap: {swap}, "
                f"OS: {os_code}, name: {name}, version: {version}, credential: {username}/{password}")

    with switch_cwd(_prepare_staging_dir(name, os_code, username, password)):
        _prepare_preseed_cfg(username, password, swap, os_code)
        _prepare_packer_json(os_code, username, password, name, version, cpu, disk, memory)
        _prepare_ovf(name, os_code, memory, cpu, disk, version)
        _prepare_customize_script(username, no_swap)

        # run_script(f'packer build -timestamp-ui -force {os_code}.json', realtime=True)
        script = f'''
mkdir -p /tmp/packer_cache
PACKER_CACHE_DIR=/tmp/packer_cache packer build -timestamp-ui -force {os_code}.json && echo "Build Sucess !"
# Do compression
rm -rf output/*.vdi
if which VBoxManage; then
    # round-trip through vdi format to get rid of deflate compression in vmdk
    for f in output/*.vmdk; do
        VBoxManage clonehd --format vdi $f $f.vdi
        VBoxManage closemedium disk --delete $f
        VBoxManage modifyhd --compact $f.vdi
        VBoxManage clonehd --format vmdk $f.vdi $f
        VBoxManage closemedium disk --delete $f.vdi
        VBoxManage closemedium disk $f
    done
fi
# Generate OVA
echo "Generating OVA ..."
sed "s/OVF_SIZE/`wc -c output/{name}-{os_code}-{version}-disk001.vmdk | awk '{{print $1}}'`/" ubuntu.ovf > output/{name}-{os_code}-{version}.ovf
cat <<EOF >output/{name}-{os_code}-{version}.mf
SHA1({name}-{os_code}-{version}-disk001.vmdk)= `sha1sum output/{name}-{os_code}-{version}-disk001.vmdk | awk '{{print $1}}'`
SHA1({name}-{os_code}-{version}.ovf)= `sha1sum output/{name}-{os_code}-{version}.ovf | awk '{{print $1}}'`
EOF
( cd output; ovftool --shaAlgorithm=SHA1 {name}-{os_code}-{version}.ovf {name}-{os_code}-{version}.ova ) && echo Done.'''
        if dry:
            click.echo(f"""(
cd {os.getcwd()};
{script}
)""")
        else:
            run_script(script, realtime=True)
            # run_script("ping -c 5 www.baidu.com", realtime=True)


def _prepare_customize_script(username, no_swap):
    logger.info("Creating customizing script ...")
    script = """
# basic
set -x
sudo apt update
sudo apt-get install python3-venv -y
sudo apt install python3-pip -y
sudo apt install python-is-python3 -y
# sudo apt install ubuntu-desktop -y
# sudo apt install vpnc -y
# sudo apt install iperf3 -y

cat <<EOF | tee $HOME/.inputrc | sudo tee /root/.inputrc
"\C-p": history-search-backward
"\C-n": history-search-forward
EOF
sudo chmod a+wr $HOME/.inputrc

cat <<EOF | sudo tee -a /etc/sudoers
{username} ALL=(ALL) NOPASSWD: ALL
EOF

cat <<EOF | sudo tee -a /etc/sudoers
cisco ALL=(ALL) NOPASSWD: ALL
EOF

cat <<EOF | tee -a $HOME/.bashrc | sudo tee -a /root/.bashrc
export TMOUT=0
alias ..='cd ..'
alias ...='.2'
EOF

# network
sudo -E bash <<EOF
echo "Create netplan config for eth0"
cat <<EOF2 >/etc/netplan/01-netcfg.yaml;
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      # dhcp6: true
EOF2

# Disable Predictable Network Interface names and use eth0
sed -i 's/en[[:alnum:]]*/eth0/g' /etc/network/interfaces;
sed -i 's/GRUB_CMDLINE_LINUX="\(.*\)"/GRUB_CMDLINE_LINUX="net.ifnames=0 biosdevname=0 \1"/g' /etc/default/grub;
update-grub;

EOF
"""
    if no_swap:
        script += """sudo swapoff -a && sudo sed -i '/ swap / s/^\\(.*\\)$/# \\1/g' /etc/fstab
"""
    with open('customize.sh', 'w') as f:
        f.write(script)

def _prepare_packer_json(os_code, username, password, name, version, cpu, disk, memory):
    logger.info("Creating packer json file ...")
    dir_path = os.path.dirname(os.path.realpath(__file__))
    rendered = ''
    with open(os.path.join(dir_path, f'{os_code}.json.template'), 'r') as f:
        tplt = Template(f.read())
        rendered = tplt.substitute({
            'username': username,
            'password': password,
            # 'staging_dir': f"{name}-{os_code}-output",
            'image_name': name,
            'version': version,
            'cpu': cpu,
            'disk': disk,
            'memory': memory,
            'os_code': os_code,
        })
    with open(f"{os_code}.json", 'w') as f:
        f.write(rendered)
    pass


def _prepare_staging_dir(name, os_code, username, password):
    cwd = os.getcwd()
    staging_dir = os.path.join(cwd, f"{name}-{os_code}-staging")
    if os.path.exists(staging_dir):
        logger.info(f"Removing existing staging dir: {staging_dir}")
        shutil.rmtree(staging_dir, ignore_errors=True)

    logger.info(f"Mkdir {staging_dir}")
    os.mkdir(staging_dir)
    logger.info("Changing CWD")
    return staging_dir


ova.add_command(ubuntu)
