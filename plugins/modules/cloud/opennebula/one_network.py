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
  user_id:
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
user_id:
    description: network's owner id
    type: int
    returned: when I(state=present)
    sample: 143
user_name:
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
            user_name=dict(type='str', required=False),
            group_name=dict(type='str', required=False),
            state=dict(type='str', choices=['present', 'absent', 'query'], default='present'),
            template=dict(type='dict', required=False),
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
        user_name = params.get('user_name')
        group_name = params.get('group_name')
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
                self.result = self.update_network(network, params, template_data)

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

    def get_user_by_name(self, user_name):
        user_pool = self.one.userpool.info()

        for user in user_pool.USER:
            if user.NAME == user_name:
                return user

        self.fail(msg="No user with name '%s' found" % user_name)

    def get_group_by_name(self, group_name):
        group_pool = self.one.grouppool.info()

        for group in group_pool.GROUP:
            if group.NAME == group_name:
                return group

        self.fail(msg="No group with name '%s' found" % group_name)

    def get_template_diff(self, existing_config, proposed_template):
        if proposed_template is None:
            proposed_template = dict()

        if self.requires_template_update(existing_config['template'], proposed_template):
            return True

        return False

    def get_parameter_diff(self, existing_config, proposed_config):
        diff_params = []
        for key in proposed_config:
            if key != 'template':
                if key in existing_config.keys() and proposed_config[key] != None:
                    if proposed_config[key] != existing_config[key]:
                        diff_params.append(key)

        return diff_params

    def create_network(self, name, network_data):
        if not self.module.check_mode:
            self.one.network.allocate("NAME = \"" + name + "\"\n" + network_data)

        result = self.get_network_info(self.get_network_by_name(name))
        result['changed'] = True

        return result

    def update_network(self, network, params, template):
        result = self.get_network_info(self.get_network_by_id(network.ID))
        result['changed'] = False

        if self.get_template_diff(result, template):
            result['changed'] = True
            if not self.module.check_mode:
                # 0 = replace the whole template
                self.one.vn.update(network.ID, template, 0)

        param_diffs = self.get_parameter_diff(result, params)
        if param_diffs:
            result['changed'] = True
            if 'user_name' in param_diffs and 'group_name' in param_diffs:
                user = self.get_user_by_name(params['user_name'])
                group = self.get_group_by_name(params['group_name'])
                self.one.vn.chown(network.ID, user.ID, group.ID)
            elif 'user_name' in param_diffs:
                user = self.get_user_by_name(params['user_name'])
                self.one.vn.chown(network.ID, user.ID, -1)
            elif 'group_name' in param_diffs:
                group = self.get_group_by_name(params['group_name'])
                self.one.vn.chown(network.ID, -1, group.ID)
            else:
                raise ValueError('Parameter diffs %s' % param_diffs)

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
