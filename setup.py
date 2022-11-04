# setup.py
import os
from setuptools import setup, find_packages

folder = os.path.dirname(os.path.realpath(__file__))
requirements_path = folder + '/requirements.txt'
install_requires = [] # ["gunicorn", "docutils>=0.3", "lxml==0.5a7"]
if os.path.isfile(requirements_path):
    with open(requirements_path) as f:
        install_requires = f.read().splitlines()

config = {
    'name' : 'corgi-tools',
    'description' : 'Tools',
    'author' : 'Hao Ruan',
    'author_email' : 'ruanhao1116@gmail.com',
    'version' : '1.0',
    'packages' : find_packages(),
    'install_requires': install_requires,
    # 'include_package_data': True, # use this option together with a MANIFEST.in
    'package_data': {
        'corgi_vcenter': ['*'],
        'corgi_misc': ['*'],
        'corgi_aws': ['*', 'templates/*'],
        'corgi_build': ['*', 'templates/*'],
        'corgi_configure': ['*', 'sh/*', 'templates/*'],
    },
    'setup_requires': ['wheel'],
    'entry_points': {
        'console_scripts': [
            'corgi_vcenter = corgi_vcenter.main:cli',
            'corgi_aws = corgi_aws.main:main',
            'corgi_build = corgi_build.main:main',
            'corgi_configure = corgi_configure.main:cli',
            'corgi_gauge = corgi_gauge.main:cli',
            'corgi_redis = corgi_redis.main:main',
            'corgi_mongo = corgi_mongo.main:main',
            'corgi_rabbit = corgi_rabbit.main:main',
            'corgi_jvm = corgi_jvm.main:main',
            'corgi_misc = corgi_misc.main:main',
            'corgi_tcpdump = corgi_tcpdump.main:main',
        ]
    },
}

setup(**config)
# end-of-setup.py
