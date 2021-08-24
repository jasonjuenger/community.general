#!/usr/bin/python
#
 # Copyright: (c) 2021, Jason Juenger <jasonjuenger@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
---
module: one_network

short_description: Manages OpenNebula networks

version_added: 3.4.0

requirements:
  - pyone

description:
  - "Manages OpenNebula networks."

options:
  id:
    description:
      - An I(id) of the network you would like to manage.  If not set then a
      - new network will be created with the given I(name).
    type: int
  name:
    description:
      - A I(name) of the network you would like to manage.  If a template with
      - the given name does not exist it will be created, otherwise it will be
      - managed by this module.
    type: str
  template:
    description:
      - A string containing the template contents.
    type: str
  cluster:
    description:
      - ID of the cluster to create the network under
    type: int
  owner_id:
    description:
      - ID of the user which will be set as the owner of the instance
    type: int
  group_id:
    description:
      - ID of the group which will be set as the group of the instance
    type: int
  state:
    description:
      - C(present) - state that is used to manage the network.
      - C(absent) - delete the network.
    choices: ["present", "absent"]
    default: present
    type: str

notes:
  - Supports C(check_mode).  Note that check mode always returns C(changed=true) for existing network, even if the network would not actually change.

extends_documentation_fragment:
  - community.general.opennebula

author:
  - "Jason Juenger (@jasonjuenger)"
'''

EXAMPLES = '''
- name: Fetch the network by id
  community.general.one_network:
    id: 34
  register: result

- name: Print the network properties
  ansible.builtin.debug:
    var: result
'''

RETURN = '''
id:
    description: network id
    type: int
    returned: when I(state=present)
    sample: 153
name:
    description: network name
    type: str
    returned: when I(state=present)
    sample: tenant_web_1
template:
    description: the parsed template
    type: dict
    returned: when I(state=present)
group_id:
    description: network's group id
    type: int
    returned: when I(state=present)
    sample: 1
group_name:
    description: network's group name
    type: str
    returned: when I(state=present)
    sample: one-users
owner_id:
    description: network's owner id
    type: int
    returned: when I(state=present)
    sample: 143
owner_name:
    description: network's owner name
    type: str
    returned: when I(state=present)
    sample: ansible-test
'''


from ansible_collections.community.general.plugins.module_utils.opennebula import OpenNebulaModule

class NetworkModule(OpenNebulaModule):
    def __init__(self):
        argument_spec = dict(
            id=dict(type='int', required=False),
            name=dict(type='str', required=False),
            owner=dict(type='int', required=False),
            group=dict(type='int', required=False),
            state=dict(type='str', choices=['present', 'absent', 'query'], default='present'),
            template=dict(type='str', required=False),
        )

        mutually_exclusive = [
            ['id', 'name']
        ]

        required_one_of = [('id', 'name')]

        required_if = [
            ['state', 'present', ['template']]
        ]

        OpenNebulaModule.__init__(self,
                                  argument_spec,
                                  supports_check_mode=True,
                                  mutually_exclusive=mutually_exclusive,
                                  required_one_of=required_one_of,
                                  required_if=required_if)

    def run(self, one, module, result):
        params = module.params
        id = params.get('id')
        name = params.get('name')
        owner = params.get('owner')
        group = params.get('group')
        desired_state = params.get('state')
        template_data = params.get('template')

        self.result = {}

        if desired_state == 'query':
            if id:
                self.result = self.get_network_info(self.get_network_by_id(id))
            elif name:
                self.result = self.get_network_info(self.get_network_by_name(name))
            else:
                module.fail_json(msg="Query requires either 'id' or 'name'")

            self.exit()

        network = self.get_network_instance(id, name)
        needs_creation = False
        if not network and desired_state != 'absent':
            if id:
                module.fail_json(msg="There is no network with id=" + str(id))
            else:
                needs_creation = True

        if desired_state == 'absent':
            self.result = self.delete_network(network)
        else:
            if needs_creation:
                self.result = self.create_network(name, template_data)
            else:
                self.result = self.update_network(network, template_data)

        self.exit()

    def get_network(self, predicate):
        # -3 means "Resources belonging to the user"
        # the other two parameters are used for pagination, -1 for both essentially means "return all"
        pool = self.one.vnpool.info(-3, -1, -1)

        for network in pool.VNET:
            if predicate(network):
                return network

        return None

    def get_network_by_id(self, network_id):
        return self.get_network(lambda network: (network.ID == network_id))

    def get_network_by_name(self, network_name):
        return self.get_network(lambda network: (network.NAME == network_name))

    def get_network_instance(self, requested_id, requested_name):
        if requested_id:
            return self.get_network_by_id(requested_id)
        else:
            return self.get_network_by_name(requested_name)

    def get_network_info(self, network):
        info = {
            'id': network.ID,
            'name': network.NAME,
            'template': network.TEMPLATE,
            'user_name': network.UNAME,
            'user_id': network.UID,
            'group_name': network.GNAME,
            'group_id': network.GID,
            'clusters': network.CLUSTERS.ID,
        }

        return info

    def create_network(self, name, network_data):
        if not self.module.check_mode:
            self.one.network.allocate("NAME = \"" + name + "\"\n" + network_data)

        result = self.get_network_info(self.get_network_by_name(name))
        result['changed'] = True

        return result

    def update_network(self, network, network_data):
        if not self.module.check_mode:
            # 0 = replace the whole template
            self.one.network.update(network.ID, network_data, 0)

        result = self.get_network_info(self.get_network_by_id(network.ID))
        if self.module.check_mode:
            # Unfortunately it is not easy to detect if the template would have changed, therefore always report a change here.
            result['changed'] = True
        else:
            # if the previous parsed template data is not equal to the updated one, this has changed
            result['changed'] = network.TEMPLATE != result['template']

        return result

    def delete_network(self, network):
        if not network:
            return {'changed': False}

        if not self.module.check_mode:
            self.one.vn.delete(network.ID)

        return {'changed': True}


def main():
    NetworkModule().run_module()


if __name__ == '__main__':
    main()
