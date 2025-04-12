import json
from pathlib import Path

from utils.bcolors import bcolors
from utils.config_loader import ConfigLoader

# Load configuration
config = ConfigLoader().get_config()

def load_filters():
    """Load filters from filters.json."""
    filters_path = Path(config.get('Paths', 'FILTERS'))
    
    if filters_path.exists():
        #print(f"{bcolors.OKBLUE}Loading filters from: {filters_path}{bcolors.ENDC}")
        with open(filters_path, 'r') as f:
            return json.load(f)
    else:
        print(f"{bcolors.FAIL}Filters file not found: {filters_path}{bcolors.ENDC}")
        return {}

def load_filters_with_path():
    """Print the filters path and return it."""
    filters_path = Path(config.get('Paths', 'FILTERS'))
    
    if filters_path.exists():
        #print(f"{bcolors.OKBLUE}Loading filters from: {filters_path}{bcolors.ENDC}")
        return filters_path
    else:
        print(f"{bcolors.FAIL}Filters file not found: {filters_path}{bcolors.ENDC}")
        return filters_path