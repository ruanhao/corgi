from datetime import datetime

def YmdHMS():
    return datetime.now().strftime("%Y%m%d%H%M%S")
