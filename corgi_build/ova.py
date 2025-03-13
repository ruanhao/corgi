import click
import logging
import os
import shutil
import json
from string import Template
from corgi_common.jinja2utils import get_rendered
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


@click.group(help="Utils for building OVA", context_settings=dict(help_option_names=['-h', '--help']))
@click.pass_context
def ova(ctx):
    pass


def _prepare_preseed_cfg(username, password, swapsize, os_code):
    os.makedirs(os.path.join('http'))
    if os_code == 'focal':
        os.makedirs(os.path.join('http', 'ubuntu'))
        os.makedirs(os.path.join('http', f'ubuntu-{os_code}'))
        logger.info("Creating common preseed config ...")
        with open(os.path.join(dir_path, 'preseed.cfg.template'), 'r') as f0:
            with open(os.path.join('http', 'ubuntu', 'preseed.cfg'), 'w') as f:
                f.write(Template(f0.read()).substitute({
                    'SWAP_SIZE': swapsize,
                    'username': username,
                    'password': password
                }))
        logger.info(f"Creating preseed config for {os_code} ...")
        with open(os.path.join(dir_path, f'preseed-{os_code}.cfg.template'), 'r') as f0:
            with open(os.path.join('http', f'ubuntu-{os_code}', 'preseed.cfg'), 'w') as f:
                f.write(Template(f0.read()).substitute({
                    'username': username,
                }))
    elif os_code in ['noble', 'jammy']:
        with open(os.path.join('http', 'meta-data'), 'w'):
            pass
        with open(os.path.join(dir_path, 'user-data.template'), 'r') as f0:
            with open(os.path.join('http', 'user-data'), 'w') as f:
                f.write(Template(f0.read()).substitute({
                    'SWAP_SIZE': swapsize,
                    'username': username,
                    'password': "$6$rounds=4096$qTkeu80w$rVbH7vdAfjnTEt9DkudHJJ1glfeNSP4Q.nLTHoeY5CfH6NuUYwEmJtsgBjNBFEAxw7L8rGTQ6ilDPRbOqFnFq/"
                }))
    else:
        raise ValueError(f"Unsupported OS code: {os_code}")


def _prepare_ovf(name, os_code, memory, cpu, disk, version):
    logger.info("Creating ovf file ...")
    rendered = ''
    template_name = 'ubuntu.ovf.template' if os_code == 'focal' else f'ubuntu-{os_code}.ovf.template'
    with open(os.path.join(dir_path, template_name), 'r') as f:
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

def _support_nat_localhostreachable():
    _, _, stderr = run_script('vboxmanage modifyvm --help', capture=True)
    return 'nat-localhostreachableN' in stderr


@click.command(help="Build Ubuntu")
@click.option('--cpu', '-c', default=4, help="CPU count", show_default=True)
@click.option('--memory', '-m', default=16384, type=int, help="Memory (MB)", show_default=True)
@click.option('--disk', '-d', default=128, type=int, help="Disk size (GB)", show_default=True)
@click.option('--swap', type=int, help="Swap size (MB)")
@click.option('--os', "os_code", default='noble', type=click.Choice(['focal', 'jammy', 'noble']), help="OS code", show_default=True)
@click.option('--name', help="OVA filename")
@click.option('--version', default='1.0.0', help="Version", show_default=True)
@click.option('--redis-version', help="Install redis")
@click.option('--username', default='cisco', help="Login username", show_default=True)
@click.option('--password', default='cisco', help="Login password", show_default=True)
@click.option('--dry', is_flag=True, help="Show script without running")
@click.option('--no-swap', is_flag=True, help="Disable swap")
def ubuntu(cpu, memory, disk, swap, os_code, name, version, username, password, dry, no_swap, redis_version):
    """
    https://github.com/alvistack/vagrant-ubuntu/blob/master/packer/ubuntu-22.04-virtualbox/packer.json

    pass on ubuntu, vboxmanage: 5.1.38_Ubuntur122592
    > corgi_build ova ubuntu -c 8 -d 64 --swap 4096 --version=22.04.3.20231104.64g
    """
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
        _prepare_customize_script(
            username=username,
            no_swap=no_swap,
            redis_version=redis_version
        )

        # run_script(f'packer build -timestamp-ui -force {os_code}.json', realtime=True)
        script = f'''
mkdir -p /tmp/packer_cache
PACKER_CACHE_DIR=/tmp/packer_cache packer build -var disk_size={disk} -timestamp-ui -force {os_code}.json && echo "Build Sucess !"
# PACKER_CACHE_DIR=/tmp/packer_cache packer build -timestamp-ui -force {os_code}.json && echo "Build Sucess !"
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


def _prepare_customize_script(**values):
    logger.info(f"Creating customizing script ... {values}")
    script = get_rendered('customize.j2', **values)
    with open('customize.sh', 'w') as f:
        f.write(script)


def _vbox_commands():
    vbox_commands = []
    if _support_nat_localhostreachable():
        vbox_commands += [
            "modifyvm",
            "{{.Name}}",
            "--nat-localhostreachable1",
            "on"
        ]
    if vbox_commands:
        return json.dumps(vbox_commands)
    else:
        return ''


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
            'vbox_commands': _vbox_commands()
        })
    with open(f"{os_code}.json", 'w') as f:
        f.write(rendered)


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
