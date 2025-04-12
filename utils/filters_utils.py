import json
from pathlib import Path

from utils.config_loader import ConfigLoader

# Load configuration
config = ConfigLoader().get_config()

def load_filters():
    """Load filters from filters.json."""
    filters_path = Path(config.get('Paths', 'FILTERS'))
    
    if filters_path.exists():
        #print(f"\033[94mLoading filters from: {filters_path}\033[0m")
        with open(filters_path, 'r') as f:
            return json.load(f)
    else:
        print(f"\033[91mFilters file not found: {filters_path}\033[0m")
        return {}

def load_filters_with_path():
    """Print the filters path and return it."""
    filters_path = Path(config.get('Paths', 'FILTERS'))
    
    if filters_path.exists():
        #print(f"\033[94mLoading filters from: {filters_path}\033[0m")
        return filters_path
    else:
        print(f"\033[91mFilters file not found: {filters_path}\033[0m")
        return filters_path