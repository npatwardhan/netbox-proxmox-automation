#!/usr/bin/env python3

import os, sys
import re
import pprint
import yaml
import urllib3
import pynetbox

from helpers.netbox_objects import __netbox_make_slug

from pynetbox.core.query import RequestError
import requests.exceptions


class NetBoxAPI:
    def __init__(self, cfg_data: dict):
        try:
            nb_url = f"{cfg_data['netbox_http_proto']}://{cfg_data['netbox_host']}:{cfg_data['netbox_port']}"
            nb_conn = pynetbox.api(url=nb_url, token=cfg_data['netbox_api_token'])
            self.nb_conn = nb_conn

            self.nb_conn.http_session.verify = False
            urllib3.disable_warnings()

        except requests.exceptions.ConnectionError as e:
            raise ValueError(f"connection error {e}")
        except RequestError as e:
            raise ValueError(f"Request error: {e} ||| {e.status_code} ||| {e.full_response}")
        except Exception as e:
            # Catch any other unexpected exceptions
            print(f"An unexpected error occurred: {type(e).__name__}")
            print(f"Error details: {e}")            


class NetBoxVirtualMachines(NetBoxAPI):
    def __init__(self, cfg_data: dict):
        super().__init__(cfg_data)

        self.collected_vms = {}
        self.collected_lxc = {}

        self.__collect_vms()


    def __collect_vms(self):
        vm_all = self.nb_conn.virtualization.virtual_machines.all()

        for vm in vm_all:
            #print("VM", dict(vm))
            if 'proxmox_vm_type' in vm['custom_fields'] and vm['custom_fields']['proxmox_vm_type'] == 'vm':
                #print(f"VM INFO: {dict(vm)} {vm['name']} ||| {vm['custom_fields']}")
                if not vm['name'] in self.collected_vms:
                    self.collected_vms[vm['name']] = {}

                self.collected_vms[vm['name']] = vm['custom_fields']

                self.collected_vms[vm['name']]['vm_name'] = vm['id']
                self.collected_vms[vm['name']]['proxmox_discovered_vm'] = False

                if 'tags' in dict(vm):
                    find_discovered_vm = list(filter(lambda pm_vm_disc: pm_vm_disc['name'] == 'proxmox-vm-discovered', vm['tags']))

                    if len(find_discovered_vm) == 1:
                        if 'name' in find_discovered_vm[0] and find_discovered_vm[0]['name'] == 'proxmox-vm-discovered':
                            self.collected_vms[vm['name']]['proxmox_discovered_vm'] = True

                del self.collected_vms[vm['name']]['proxmox_vm_type']
                del self.collected_vms[vm['name']]['proxmox_node']

    
class NetBoxVirtualMachinesCustomObjects(NetBoxAPI):
    def __init__(self, cfg_data: dict):
        super().__init__(cfg_data)

        self.existing_vm_co = {}
        self.__get_existing_nb_vmco()


    def __get_existing_nb_vmco(self):
        for existing_co_vm in list(self.nb_conn.plugins.custom_objects.proxmox_vms.all()):
            self.existing_vm_co[dict(existing_co_vm)['display']] = dict(existing_co_vm)['proxmox_vmid']
    

    def create_nb_vm_co(self, vm_name: str, payload: dict):
        if not vm_name in self.existing_vm_co:
            nb_obj = self.nb_conn.plugins.custom_objects.proxmox_vms.create(**payload)
            self.existing_vm_co[dict(nb_obj)['display']] = dict(nb_obj)['proxmox_vmid']

        return self.existing_vm_co[vm_name]


class NetBoxCustomObjectsAndFields(NetBoxAPI):
    def __init__(self, cfg_data: dict):
        super().__init__(cfg_data)

        self.co_id_mappings = {}
        self.__collect_nb_custom_objects()

    
    def __collect_nb_custom_objects(self):
        for cot in self.nb_conn.plugins.custom_objects.custom_object_types.all():
            cot_info = dict(cot)

            if not 'name' in cot_info:
                raise ValueError(f"Missing 'name' in {cot}")

            if not 'id' in cot_info:
                raise ValueError(f"Missing 'id' in {cot}")
            
            self.co_id_mappings[cot_info['name']] = cot_info['id']


    def nb_create_custom_object(self, co_name: str, co_slug: str):
        if not co_name in self.co_id_mappings:
            nb_obj = self.nb_conn.plugins.custom_objects.custom_object_types.create(
                name = co_name,
                #verbose_name = co_name,
                #verbose_name_plural = f"{co_name}s",
                slug = co_slug
            )
            nb_obj_dict = dict(nb_obj)

            self.co_id_mappings[nb_obj_dict['name']] = nb_obj_dict['id']


    def nb_create_custom_object_field(self, co_field_data: dict):
        self.nb_conn.plugins.custom_objects.custom_object_type_fields.create(co_field_data)


def main():
    netbox_cfg = 'netbox.yml'

    with open(netbox_cfg) as nb_f:
        nb_f = yaml.safe_load(nb_f)

    nb_vm_obj = NetBoxVirtualMachines(nb_f)

    for collected_vm in nb_vm_obj.collected_vms:
        nb_migrate_vm_co = NetBoxVirtualMachinesCustomObjects(nb_f)
        nb_migrate_vm_co.create_nb_vm_co(collected_vm, nb_vm_obj.collected_vms[collected_vm])

    sys.exit(0)


if __name__ == "__main__":
    main()
