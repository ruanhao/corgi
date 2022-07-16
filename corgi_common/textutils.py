import re

def extract(regex, string):
    m = re.match(regex, string)
    if m:
        return m.groups()
