import re

def extract(regex, string):
    m = re.match(regex, string)
    if m:
        return m.groups()

# multiline
def extract_mp(regex, para):
    return re.findall(regex, para)
