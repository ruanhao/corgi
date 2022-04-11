from .common import VCRestAgent


class Agent(VCRestAgent):

    def list_networks(self):
        url = f"https://{self.host}/rest/vcenter/network"
        return self.get(url)
