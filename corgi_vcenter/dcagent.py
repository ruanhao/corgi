from .common import VCRestAgent


class Agent(VCRestAgent):

    def list_dcs(self):
        url = f"https://{self.host}/rest/vcenter/datacenter"
        return self.get(url)
