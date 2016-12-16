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
module: infini_export_client
version_added: 2.3
short_description: Create, Delete or Modify NFS Client(s) for existing export on Infinibox
description:
    - This module creates, deletes or modifys NFS Client(s) for existing export on Infinibox.
options:
  client:
    description:
      - Client IP or Range. Ranges can be defined as follows
        192.168.0.1-192.168.0.254
    aliases: ['name']
    required: true
  state:
    description:
      - Creates/Modifies client when present and removes when absent
    required: false
    default: "present"
    choices: [ "present", "absent" ]
  access_mode:
    description:
      - Read Write or Read Only Access
    choices: [ "RW", "RO" ]
    default: RW
    required: false
  no_root_squash:
    description:
      - Don't squash root user to anonymous. Will be set to "no" on creation if not specified explicitly.
    choices: [ "yes", "no" ]
    default: no
    required: false
  export:
    description:
      - Name of the export
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
# Make sure nfs client 10.0.0.1 is configured for export. Allow root access
- infini_export_client: client=10.0.0.1 access=RW no_root_squash=yes export=/data system=ibox01

# Add multiple clients with RO access. Squash root priviledges
- infini_export_client: client={{ item }} access=RO no_root_squash=no export=/data system=ibox01
  with_items:
    - 10.0.0.2
    - 10.0.0.3
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
from munch import Munch, unmunchify


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
def get_export(module, system):
    """Retrun export if found. Fail module if not found"""

    try:
        export = system.exports.get(export_path=module.params['export'])
    except:
        module.fail_json(msg="Export with export path {} not found".format(module.params['export']))

    return export


@api_wrapper
def update_client(module, export):
    """Update export client list"""

    changed = False

    client         = module.params['client']
    access_mode    = module.params['access_mode']
    no_root_squash = module.params['no_root_squash']

    client_list        = export.get_permissions()
    client_not_in_list = True

    for index, item in enumerate(client_list):
        if item.client == client:
            client_not_in_list = False
            if item.access != access_mode:
                item.access = access_mode
                changed = True
            if item.no_root_squash is not no_root_squash:
                item.no_root_squash = no_root_squash
                changed = True

    # If access_mode and/or no_root_squash not passed as arguments to the module,
    # use access_mode with RW value and set no_root_squash to False
    if client_not_in_list:
        changed = True
        client_list.append(Munch(client=client, access=access_mode, no_root_squash=no_root_squash))

    if changed:
        for index, item in enumerate(client_list):
            client_list[index] = unmunchify(item)
        export.update_permissions(client_list)

    module.exit_json(changed=changed)


@api_wrapper
def delete_client(module, export):
    """Update export client list"""

    changed = False

    client      = module.params['client']
    client_list = export.get_permissions()

    for index, item in enumerate(client_list):
        if item.client == client:
            changed = True
            del client_list[index]

    if changed:
        for index, item in enumerate(client_list):
            client_list[index] = unmunchify(item)
        export.update_permissions(client_list)

    module.exit_json(changed=changed)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            client         = dict(required=True),
            access_mode    = dict(choices=['RO', 'RW'], default='RW'),
            no_root_squash = dict(type='bool', default='no'),
            state          = dict(default='present', choices=['present', 'absent']),
            export         = dict(required=True),
            system         = dict(required=True),
            user           = dict(no_log=True),
            password       = dict(no_log=True),
        ),
        supports_check_mode=False
    )

    if not HAS_INFINISDK:
        module.fail_json(msg='infinisdk is required for this module')

    system     = get_system(module)
    export     = get_export(module, system)

    if module.params['state'] == 'present':
        update_client(module, export)
    else:
        delete_client(module, export)

# Import Ansible Utilities
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
