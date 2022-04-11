from .common import VCRestAgent


class Agent(VCRestAgent):

    def list_dsz(self):
        url = f"https://{self.host}/rest/vcenter/datastore"
        return self.get(url)
