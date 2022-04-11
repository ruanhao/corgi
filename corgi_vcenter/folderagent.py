from .common import VCRestAgent


class Agent(VCRestAgent):

    def list_folders(self, names=None):
        params = {}
        if names:
            params['filter.names'] = names
        url = f"https://{self.host}/rest/vcenter/folder"
        return self.get(url, params=params)
