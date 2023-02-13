import stackinator.utility as util 

class Metadata:
    def __init__(self, build, recipe):
        self._build = build
        self._recipe = recipe
        self._hostname = util.get_hostname()
