from .common import VCRestAgent
import logging

logger = logging.getLogger(__name__)

class Agent(VCRestAgent):

    def list_vms(self, power_states=None, hosts=None, folder_ids=None):
        params = {}
        if power_states:
            params['filter.power_states'] = power_states
        if hosts:
            params['filter.hosts'] = hosts
        if folder_ids:
            params['filter.folders'] = folder_ids
        url = f"https://{self.host}/rest/vcenter/vm"
        return self.get(url, params=params)

    def show_vm(self, vm):
        url = f"https://{self.host}/rest/vcenter/vm/{vm}"
        return self.get(url)

    def poweroff(self, vm):
        url = f"https://{self.host}/rest/vcenter/vm/{vm}/power/stop"
        logger.info(f"Powering off VM {vm} ...")
        return self.post(url)

    def delete_vm(self, vm):
        url = f"https://{self.host}/rest/vcenter/vm/{vm}"
        logger.info(f"Deleting VM {vm} ...")
        return self.delete(url)
