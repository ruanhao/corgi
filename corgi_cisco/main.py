#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import click
import base64
from functools import lru_cache
from corgi_common import config_logging, pretty_print, cached
from corgi_common.loggingutils import debug, info
from corgi_common.dateutils import time_str
import logging
import requests
import ciscoisesdk
from ciscoisesdk import IdentityServicesEngineAPI
from ciscoisesdk.exceptions import ApiError

import inspect

logger = logging.getLogger(__name__)

ISE_ERS_URL_NETWORKDEVICE = '/ers/config/networkdevice'

def _color0(v):
    return click.style(str(v), fg='red')

def _color(v, func):
    if func(v):
        return click.style(str(v), fg='red')
    else:
        return str(v)

@cached
def _ise_restful_session(ctx):
    username = ctx.obj['username']
    password = ctx.obj['password']
    hostname = ctx.obj['hostname']
    port = ctx.obj['port']

    s = requests.Session()
    s.verify = False
    url_versioninfo = f'https://{hostname}:{port}/ers/config/sgt/versioninfo'

    r = s.get(ic(url_versioninfo), auth=(ic(username), ic(password)), headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-CSRF-TOKEN': 'fetch'
    })
    assert r.ok, r.text
    csrf = r.headers.get('X-CSRF-Token')
    if csrf:                    # csrf enabled
        s.headers = {
            'X-CSRF-Token': csrf,
            'ACCEPT': 'application/json',
        }
        pass
    return s

def _ise_search_resource(ctx, path, page=1, size=100):
    s = _ise_restful_session(ctx)
    url = f"https://{ctx.obj['hostname']}:{ctx.obj['port']}/{path.lstrip('/')}"
    r = s.get(ic(url), params={'page': page, 'size': size})
    assert r.ok, r.text
    response = r.json()
    data = ic(response)['SearchResult']['resources']
    return data

def _ise_get_by_id(ctx, path, id):
    s = _ise_restful_session(ctx)
    url = f"https://{ctx.obj['hostname']}:{ctx.obj['port']}/{path.strip('/')}/{id}"
    r = s.get(ic(url))
    assert r.ok, r.text
    response = r.json()
    data = list(ic(response).values())[0]
    return data

@click.group(help="CLI tool for Cisco products")
# @click.version_option()
def cli():
    pass

@cli.group(help='cli for ISE')
@click.pass_context
@click.option('--username', '-u', envvar='CORGI_CISCO_ISE_USERNAME', default='admin')
@click.option('--hostname', envvar='CORGI_CISCO_ISE_HOSTNAME', default='10.74.107.227', show_default=True)
@click.option('--port', envvar='CORGI_CISCO_ISE_PORT', default=9060, type=int)
@click.option('--password', '-p', envvar='CORGI_CISCO_ISE_PASSWORD', default='Crdc1@3!')
@click.option('--json', '-json', 'as_json', is_flag=True)
@click.option('-x', is_flag=True)
def ise(ctx, hostname, port, username, password, as_json, x):
    ctx.ensure_object(dict)
    ctx.obj['username'] = username
    ctx.obj['password'] = password
    ctx.obj['hostname'] = hostname
    ctx.obj['port'] = port
    ctx.obj['as_json'] = as_json
    ctx.obj['x'] = x
    ctx.obj['api'] = _ise_api(ctx)
    pass

def _ise_api(ctx, version='3.1_Patch_1'):
    """https://developer.cisco.com/docs/identity-services-engine/v1/
    https://ciscoisesdk.readthedocs.io/en/latest/api/api.html
    https://github.com/CiscoISE/ciscoisesdk
    """
    username = ctx.obj['username']
    password = ctx.obj['password']
    hostname = ctx.obj['hostname']
    base_url = f'https://{hostname}:9060'
    return IdentityServicesEngineAPI(
        username=ic(username),
        password=ic(password),
        uses_api_gateway=True,
        base_url=ic(base_url),
        version=version,
        verify=False,
        debug=logger.isEnabledFor(logging.DEBUG),
        uses_csrf_token=True
    )

def _gui_url(ctx, path):
    hostname = ctx.obj['hostname']
    gui_url = f"https://{hostname}/{path.lstrip('/')}"
    return ic(gui_url)

def _ise_gui_session(ctx):
    username = ctx.obj['username']
    password = ctx.obj['password']

    s = requests.Session()
    s.verify = False

    login_jsp_url = _gui_url(ctx, '/admin/login.jsp')
    debug(f"GET {login_jsp_url}")
    r = s.get(login_jsp_url, headers={
        # 'Referer': _gui_url(ctx, '/admin/')
    })
    assert r.ok, r.text

    auth_action_url = _gui_url(ctx, '/admin/adminAuthenticationAction.do')
    debug(f"GET {auth_action_url}")
    r = s.get(auth_action_url, headers={
        '_QPH_': 'Y29tbWFuZD1sb2FkSWRlbnRpdHlTdG9yZXM=',
        'Content-Type': 'application/x-www-form-urlencoded',
        # "Referer": login_jsp_url,
        'X-Requested-With': 'XMLHttpRequest'
    })
    debug("  <=" + r.text.strip())
    assert r.ok, r.text

    login_action_url = _gui_url(ctx, "/admin/LoginAction.do")
    debug(f"POST {login_action_url}")
    r = s.post(login_action_url, data=dict(
        username=username,
        password=password,
        rememberme='on',
        name=username,
        authType='Internal',
        locale='en',
        hasSelectedLocale=False,
    ), headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        # "Referer": login_jsp_url,
    })
    assert r.ok, r.text
    return s


@ise.command()
@click.pass_context
def radius_live_logs(ctx):
    session = _ise_gui_session(ctx)
    r = session.get(
        _gui_url(ctx, '/admin/rs/uiapi/mnt/authLiveLog'),
        headers={
            "_QPH_": base64.b64encode('startAt=1&pageSize=200&total_pages=0&total_entries=0'.encode('ascii')),
            'X-Requested-With': 'XMLHttpRequest, XMLHttpRequest'
        },
    )
    assert r.ok, r.text
    response = r.json()
    response = filter(lambda x: 'date' in x, response)
    response = sorted(response, key=lambda x: x['time'])
    mappings = {
        'time': ('date', time_str),
        'username': 'username',
        # 'method': 'authentication',
        'auth protocol': 'authProtocol',
        'status': ('', lambda x: click.style(x['statusTooltip'], fg=x.get('textColor'))),
        'reason': 'possibleRootCause',
        'auth policy': 'matchedAuthruleDrilldown',
        'authz policy': 'matchedAuthZruleDrilldown',
        'authz profile': 'selectedAuthorizationProfile',
    }
    if not ctx.obj['x']:
        del mappings['auth policy']
        del mappings['authz policy']
        del mappings['authz profile']
    pretty_print(response, mappings=mappings, as_json=ctx.obj['as_json'], x=ctx.obj['x'])
    pass

def _resources(gen) -> list:
    resources = []
    for page_resp in gen:
        page_result = page_resp.response.SearchResult
        for resource in page_result.resources:
            resources.append(resource)
    return resources

def _resource(rest_response: ciscoisesdk.restresponse.RestResponse):
    response = rest_response.response
    assert len(response) == 1, response
    data = list(ic(response).values())[0]
    return data


def _get_iplist(raw_iplist: str):
    iplist = []
    for group in raw_iplist.split(','):
        ipaddress, mask = group.split('/')
        iplist.append(dict(ipaddress=ipaddress, mask=int(mask)))
    return ic(iplist)


@ise.command()
@click.pass_context
@click.option('--ip-list', default='0.0.0.0/0')
@click.option('--network-protocol', default='RADIUS')
@click.option('--radius_shared_secret', default='12345678')
@click.argument("name", required=True)
def network_device_create(ctx,
                          name,  # network device name
                          ip_list, network_protocol, radius_shared_secret,
                          ):
    api = _ise_api(ctx)
    api.network_device.create_network_device(
        authentication_settings={
            "networkProtocol": network_protocol,
            'radiusSharedSecret': radius_shared_secret,
        },
        coa_port=1700,
        network_device_iplist=_get_iplist(ip_list),
        name=name,
    )

@ise.command()
@click.pass_context
def network_devices(ctx):
    """Administration/Network Resources/Network Devices"""
    api = _ise_api(ctx)
    gen = api.network_device.get_network_device_generator()

    # devices = _ise_search_resource(ctx, ISE_ERS_URL_NETWORKDEVICE)

    data = []
    for device in _resources(gen):
        # dinfo = _ise_get_by_id(ctx, ISE_ERS_URL_NETWORKDEVICE, device['id'])
        dinfo = _resource(api.network_device.get_by_id(device['id']))
        data.append({
            'name': dinfo['name'],
            'profile': dinfo['profileName'],
            'groups': '\n'.join(dinfo['NetworkDeviceGroupList']),
            'ips': '\n'.join([f"{item['ipaddress']}/{item['mask']}" for item in dinfo['NetworkDeviceIPList']]),
            'radius_secret': dinfo.get('authenticationSettings', {}).get('radiusSharedSecret', ''),
        })

    pretty_print(data, mappings={
        'name': 'name',
        'profile': 'profile',
        'groups': 'groups',
        'ips': 'ips',
        'radius_secret': 'radius_secret'
    }, as_json=ctx.obj['as_json'], x=ctx.obj['x'])

@lru_cache
def _group_name(ctx, group_id, api=None):
    api = api or _ise_api(ctx)
    group = _resource(api.identity_groups.get_by_id(group_id))
    # print(group)
    return group['name']

@lru_cache
def _profile_name(ctx, profile_id, api=None):
    api = api or _ise_api(ctx)
    profile = _resource(api.profiler_profile.get_by_id(profile_id))
    # print(group)
    return profile['name']

@ise.command()
@click.pass_context
@click.option('--username', '-u', required=True)
@click.option('--password', '-p', required=True)
@click.option('--groups', '-g', help='associated groups')
def internal_user_create(ctx, username, password, groups):
    api = _ise_api(ctx)
    group_ids = None
    if groups:
        group_ids = groups.split(',')
    api.internal_user.create(
        enabled=True,
        change_password=False,
        identity_groups=group_ids,
        name=username,
        password=password,
        expiry_date_enabled=False,
    )
    pass

@ise.command()
@click.pass_context
@click.option('--name', '-n', required=True)
@click.option('--desc', '-d', default="created by Hao")
def identity_group_create(ctx, name, desc):
    api = _ise_api(ctx)
    api.identity_groups.create_identity_group(
        name=name,
        description=desc
    )

@ise.command(help='Enpoint')
@click.pass_context
def endpoints(ctx):
    api = ctx.obj['api']
    endpoints_generator = api.endpoint.get_endpoints_generator()
    data = []
    for endpoint in _resources(endpoints_generator):
        e_id = endpoint['id']
        e = api.endpoint.get_by_id(e_id).response['ERSEndPoint']
        # e_mac = e['mac']
        # e_profile_id = e['profileId']
        # e_group_id = e['groupId']
        data.append(e)
        # data.append(dict(
        # ))
    pretty_print(data, mappings={
        'id': 'id',
        'mac': 'mac',
        'group': ('groupId', lambda gid: _group_name(ctx, gid, api)),
        'group assignment': ('staticGroupAssignment', lambda b: 'y' if b else ''),
        'profile': ('profileId', lambda pid: _profile_name(ctx, pid, api)),
        'profile assignment': ('staticProfileAssignment', lambda b: 'y' if b else ''),
    }, as_json=ctx.obj['as_json'], x=ctx.obj['x'])
    pass

@ise.command(help='User identity groups')
@click.pass_context
def identity_groups(ctx):
    api = _ise_api(ctx)
    group_generator = api.identity_groups.get_identity_groups_generator()
    data = []
    for group in _resources(group_generator):
        data.append(dict(
            id=group['id'],
            name=group['name'],
            desc=group['description']
        ))
    pretty_print(data, mappings={
        'id': 'id',
        'name': 'name',
        'desc': 'desc',
    }, as_json=ctx.obj['as_json'], x=ctx.obj['x'])

@ise.command()
@click.pass_context
def internal_users(ctx):
    api = _ise_api(ctx)
    user_generator = api.internal_user.get_internal_user_generator()
    data = []
    for user0 in _resources(user_generator):
        user = _resource(api.internal_user.get_by_id(user0['id']))
        group_names = []
        if 'identityGroups' in ic(user):
            for group_id in user['identityGroups'].split(','):
                group_names.append(_group_name(ctx, group_id, api=api))
        data.append(dict(
            name=user['name'],
            enabled=user['enabled'],
            groups=group_names,
            id_store=user['passwordIDStore'],
            change_password=user['changePassword'],
        ))
    pretty_print(data, mappings={
        'name': 'name',
        'enabled': 'enabled',
        'change password': 'change_password',
        'id store': 'id_store',
        'groups': 'groups',
    })
    pass


def main():
    config_logging('corgi_cisco')
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
