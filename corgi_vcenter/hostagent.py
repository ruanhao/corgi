from .common import VCRestAgent


class Agent(VCRestAgent):

    def list_hosts(self):
        url = f"https://{self.host}/rest/vcenter/host"
        return self.get(url)
