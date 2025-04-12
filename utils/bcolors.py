class bcolors:
    ENDC = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BCyan = '\033[1;36m'
    FAIL = '\033[91m'
    WARNING = '\033[93m'
    OKGREEN = '\033[92m'
    OKBLUE = '\033[94m'
    HEADER = '\033[95m'
    ICyan = '\033[96m'

    def __init__(self):
        pass

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''