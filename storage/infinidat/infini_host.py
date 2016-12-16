#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2016, Gregory Shulov (gregory.shulov@gmail.com)
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: infini_host
version_added: 2.3
short_description: Create, Delete and Modify Host on Infinibox
description:
    - An Ansible module to Create, Delete or Modify Host on Infinibox.
options:
  name:
    description:
      - Host Name
    required: true
  state:
    description:
      - Creates/Modifies Host when present or removes when absent
    required: false
    default: present
    choices: [ "present", "absent" ]
  wwns:
    description:
      - List of wwns of the host
    required: false
  volume:
    description:
      - Volume name to map to the host
    required: false
  system:
    description:
      - Infinibox hostname or IP Address
    required: true
  user:
    description:
      - Infinibox User username
    required: false
  password:
    description:
      - Infinibox User password
    required: false
notes:
  - This module requires infinisdk python library.
  - You must set INFINIBOX_USER and INFINIBOX_PASSWORD environment variables
    if user and password arguments are not passed to the module directly.
  - Ansible uses the infinisdk configuration file (~/.infinidat/infinisdk.ini) if no credentials are provided.
    See http://infinisdk.readthedocs.io/en/latest/getting_started.html
requirements:
  - "python >= 2.7"
  - infinisdk
author: Gregory Shulov
'''

EXAMPLES = '''
# Create new new host
- infini_host: name=foo.example.com system=ibox01

# Make sure host bar is available with wwn ports
- infini_host:
    name: bar.example.com
    wwns:
      - "00:00:00:00:00:00:00"
      - "11:11:11:11:11:11:11"
    system: ibox01

# Map host foo.example.com to volume bar
- infini_host:
    name: foo.example.com
    volume: bar
    system: ibox01
'''

RETURN = '''
'''

HAS_INFINISDK = True
try:
    from infinisdk import InfiniBox, core
except ImportError:
    HAS_INFINISDK = False

from functools import wraps
from capacity import *
from os import environ
from os import path
from collections import Counter


def api_wrapper(func):
    """ Catch API Errors Decorator"""
    @wraps(func)
    def __wrapper(*args, **kwargs):
        module = args[0]
        try:
            return func(*args, **kwargs)
        except core.exceptions.APICommandException as e:
            module.fail_json(msg=e.message)
        except core.exceptions.SystemNotFoundException as e:
            module.fail_json(msg=e.message)
        except:
            raise
    return __wrapper


@api_wrapper
def get_system(module):
    """Return System Object or Fail"""
    box      = module.params['system']
    user     = module.params['user']
    password = module.params['password']

    if user and password:
        system = InfiniBox(box, auth=(user, password))
    elif environ.get('INFINIBOX_USER') and environ.get('INFINIBOX_PASSWORD'):
        system = InfiniBox(box, auth=(environ.get('INFINIBOX_USER'), environ.get('INFINIBOX_PASSWORD')))
    elif path.isfile(path.expanduser('~') + '/.infinidat/infinisdk.ini'):
        system = InfiniBox(box)
    else:
        module.fail_json(msg="You must set INFINIBOX_USER and INFINIBOX_PASSWORD environment variables or set username/password module arguments")

    try:
        system.login()
    except Exception:
        module.fail_json(msg="Infinibox authentication failed. Check your credentials")
    return system


@api_wrapper
def get_host(module, system):

    host  = None

    for h in system.hosts.to_list():
        if h.get_name() == module.params['name']:
            host = h
            break

    return host


@api_wrapper
def create_host(module, system):

    changed = True
    host    = system.hosts.create(name=module.params['name'])

    if module.params['wwns']:
        for p in module.params['wwns']:
            host.add_fc_port(p)
    # if module.params['iqns']:
    #     for i in module.params['iqns']:
    #         pass
    if module.params['volume']:
        host.map_volume(system.volumes.get(name=module.params['volume']))
    module.exit_json(changed=changed)


@api_wrapper
def update_host(module, host):

    changed = False
    name    = module.params['name']

    module.exit_json(changed=changed)


@api_wrapper
def delete_host(module, host):
    changed = True
    host.delete()
    module.exit_json(changed=changed)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name      = dict(required=True),
            state     = dict(default='present', choices=['present', 'absent']),
            wwns      = dict(type='list'),
            volume    = dict(),
            system    = dict(required=True),
            user      = dict(),
            password  = dict(),
        ),
        supports_check_mode=False
    )

    if not HAS_INFINISDK:
        module.fail_json(msg='infinisdk is required for this module')

    state  = module.params['state']
    system = get_system(module)
    host   = get_host(module, system)

    if module.params['volume']:
        try:
            system.volumes.get(name=module.params['volume'])
        except:
            module.fail_json(msg='Volume {} not found'.format(module.params['volume']))

    if host and state == 'present':
        update_host(module, host)
    elif host and state == 'absent':
        delete_host(module, host)
    elif host is None and state == 'absent':
        module.exit_json(changed=False)
    else:
        create_host(module, system)


# Import Ansible Utilities
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
