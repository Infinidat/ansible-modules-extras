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
module: infini_export
version_added: 2.3
short_description: Create, Delete or Modify NFS Export on Infinibox
description:
    - This module creates, deletes or modifies NFS Exports on Infinibox.
options:
  name:
    description:
      - Export name. Should always start with \"/\". (ex. name=/data)
    aliases: ['export', 'path']
    required: true
  state:
    description:
      - Creates/Modifies export when present and removes when absent
    required: false
    default: "present"
    choices: [ "present", "absent" ]
  inner_path:
    description:
      - Internal path of the export
    default: "/"
  client_list:
    description:
      - List of dictionaries with client entries. See examples.
        Check infini_export_client module to modify individual NFS client entries for export
    default: "All Hosts(*), RW, no_root_squash: True"
    required: false
  filesystem:
    description:
      - Name of exported file system
    required: true
  system:
    description:
      - Infinibox hostname or IP address
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
# Export bar filesystem under foo pool as /data
- infini_export: name=/data01 filesystem=foo system=ibox001

# Export and specify client list explictly
- infini_export:
  name: /data02
  filesystem: foo
  client_list:
    - client: 192.168.0.2
      access: RW
      no_root_squash: True
    - client: 192.168.0.100
      access: RO
      no_root_squash: False
    - client: 192.168.0.10-192.168.0.20
      access: RO
      no_root_squash: False
  system: ibox001
'''

RETURN = '''
'''

HAS_INFINISDK = True
try:
    from infinisdk import InfiniBox, core
except ImportError:
    HAS_INFINISDK = False

from functools import wraps
from os import environ
from os import path
from munch import unmunchify


def transform(d):
    return frozenset(d.items())


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
def get_filesystem(module, system):
    """Return Filesystem or None"""
    try:
        return system.filesystems.get(name=module.params['filesystem'])
    except:
        return None


@api_wrapper
def get_export(module, filesystem, system):
    """Retrun export if found. When not found return None"""

    export = None
    exports_to_list = system.exports.to_list()

    for e in exports_to_list:
        if e.get_export_path() == module.params['name']:
            export = e
            break

    return export


@api_wrapper
def update_export(module, export, filesystem, system):
    """ Create new filesystem or update existing one"""

    changed = False

    name = module.params['name']
    client_list = module.params['client_list']

    if export is None:
        export = system.exports.create(export_path=name, filesystem=filesystem)
        if client_list:
            export.update_permissions(client_list)
        changed = True
    else:
        if client_list:
            if set(map(transform, unmunchify(export.get_permissions()))) != set(map(transform, client_list)):
                export.update_permissions(client_list)
                changed = True

    module.exit_json(changed=changed)


@api_wrapper
def delete_export(module, export):
    """ Delete file system"""
    export.delete()
    module.exit_json(changed=True)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name        = dict(required=True),
            state       = dict(default='present', choices=['present', 'absent']),
            filesystem  = dict(required=True),
            client_list = dict(type='list'),
            system      = dict(required=True),
            user        = dict(no_log=True),
            password    = dict(no_log=True),
        ),
        supports_check_mode=False
    )

    if not HAS_INFINISDK:
        module.fail_json(msg='infinisdk is required for this module')

    state      = module.params['state']
    system     = get_system(module)
    filesystem = get_filesystem(module, system)
    export     = get_export(module, filesystem, system)

    if filesystem is None:
        module.fail_json(msg='Filesystem {} not found'.format(module.params['filesystem']))

    if state == 'present':
        update_export(module, export, filesystem, system)
    elif export and state == 'absent':
        delete_export(module, export)
    elif export is None and state == 'absent':
        module.exit_json(changed=False)


# Import Ansible Utilities
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
