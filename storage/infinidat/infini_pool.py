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
module: infini_pool
version_added: 2.3
short_description: Create, Delete and Modify Pool on Infinibox
description:
    - An Ansible module to Create, Delete or Modify Pools on Infinibox.
options:
  name:
    description:
      - Pool Name
    required: true
  state:
    description:
      - Creates/Modifies Pool when present or removes when absent
    required: false
    default: present
    choices: [ "present", "absent" ]
  size:
    description:
      - Pool Physical Capacity in MB, GB or TB units.
        If pool size is not set on pool creation, size will be equal to 1TB.
        See examples.
    required: false
  vsize:
    description:
      - Pool Virtual Capacity in MB, GB or TB units.
        If pool vsize is not set on pool creation, Virtual Capacity will be equal to Physical Capacity.
        See examples.
    required: false
  ssd_cache:
    description:
      - Enable/Disable SSD Cache on Pool
    required: false
    default: yes
    choices: [ "yes", "no" ]
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
# Make sure pool foo exists. Set pool physical capacity to 10TB.
# For new pool virtual capacity will be set to 10TB
- infini_pool: name=foo size=10TB system=ibox01

# Disable SSD Cache on pool
- infini_pool: name=foo ssd_cache=no system=ibox01

# Update pool virtual_capacity. Authenticate using user and password variables.
# When credentials are included in playbook, make sure the encrypt variable files with ansible-vault.
- infini_pool: name=foo vsize=300TB system=ibox01 user=admin password=secret
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
def get_pool(module, system):
    """Return Pool on None"""
    try:
        return system.pools.get(name=module.params['name'])
    except:
        return None


@api_wrapper
def create_pool(module, system):
    """Create Pool"""
    name      = module.params['name']
    size      = module.params['size']
    vsize     = module.params['vsize']
    ssd_cache = module.params['ssd_cache']

    if not size and not vsize:
        pool = system.pools.create(name=name, physical_capacity=Capacity('1TB'), virtual_capacity=Capacity('1TB'))
    elif size and not vsize:
        pool = system.pools.create(name=name, physical_capacity=Capacity(size), virtual_capacity=Capacity(size))
    elif not size and vsize:
        pool = system.pools.create(name=name, physical_capacity=Capacity('1TB'), virtual_capacity=Capacity(vsize))
    else:
        pool = system.pools.create(name=name, physical_capacity=Capacity(size), virtual_capacity=Capacity(vsize))

    # Default value of ssd_cache is True. Disable ssd chacing if False
    if not ssd_cache:
        pool.update_ssd_enabled(ssd_cache)

    module.exit_json(changed=True)


@api_wrapper
def update_pool(module, system, pool):
    """Update Pool"""
    changed   = False

    size      = module.params['size']
    vsize     = module.params['vsize']
    ssd_cache = module.params['ssd_cache']

    # Roundup the capacity to mimic Infinibox behaviour
    if size:
        physical_capacity = Capacity(size).roundup(6 * 64 * KiB)
        if pool.get_physical_capacity() != physical_capacity:
            pool.update_physical_capacity(physical_capacity)
            changed = True

    if vsize:
        virtual_capacity = Capacity(vsize).roundup(6 * 64 * KiB)
        if pool.get_virtual_capacity() != virtual_capacity:
            pool.update_virtual_capacity(virtual_capacity)
            changed = True

    if pool.get_ssd_enabled() != ssd_cache:
        pool.update_ssd_enabled(ssd_cache)
        changed = True

    module.exit_json(changed=changed)


@api_wrapper
def delete_pool(module, pool):
    """Delete Pool"""
    pool.delete()
    module.exit_json(changed=True)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name      = dict(required=True),
            state     = dict(default='present', choices=['present', 'absent']),
            size      = dict(),
            vsize     = dict(),
            ssd_cache = dict(type='bool', default=True),
            system    = dict(required=True),
            user      = dict(),
            password  = dict(),
        ),
        supports_check_mode=False
    )

    if not HAS_INFINISDK:
        module.fail_json(msg='infinisdk is required for this module')

    if module.params['size']:
        try:
            Capacity(module.params['size'])
        except:
            module.fail_json(msg='size (Physical Capacity) should be define in MB, GB, TB or PB units')

    if module.params['vsize']:
        try:
            Capacity(module.params['vsize'])
        except:
            module.fail_json(msg='vsize (Virtual Capacity) should be define in MB, GB, TB or PB units')

    state  = module.params['state']
    system = get_system(module)
    pool   = get_pool(module, system)

    if state == 'present' and not pool:
        create_pool(module, system)
    elif state == 'present' and pool:
        update_pool(module, system, pool)
    elif state == 'absent' and pool:
        delete_pool(module, pool)
    elif state == 'absent' and not pool:
        module.exit_json(changed=False)


# Import Ansible Utilities
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
