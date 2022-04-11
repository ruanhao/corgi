from .common import VCRestAgent


class Agent(VCRestAgent):

    def list_resource_pools(self, hosts=None):
        params = {}
        if hosts:
            params['filter.hosts'] = hosts
        url = f"https://{self.host}/rest/vcenter/resource-pool"
        return self.get(url, params=params)
