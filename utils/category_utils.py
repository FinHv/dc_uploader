import os
import re
from configparser import ConfigParser

from .filters_utils import load_filters


def load_config(config_file='config.ini'):
    """Load the configuration from the specified file."""
    config = ConfigParser()
    config.read(config_file)
    return config

def check_for_mp3_files(directory_path):
    """Check if there are any .mp3 files in the given directory."""
    try:
        for filename in os.listdir(directory_path):
            if filename.lower().endswith('.mp3'):
                return True
    except FileNotFoundError:
        print(f"\033[33mDirectory not found: {directory_path}\033[0m")
    return False

def determine_category(directory_name):
    """Determine the category of the content based on directory name using filters from filters.json."""
    filters = load_filters()
    config = load_config()  # Load configuration
    data_dir = config.get('Paths', 'DATADIR').strip()  # Get DATADIR from config
    full_directory_path = os.path.join(data_dir, directory_name)
    
    if not filters:
        print("\033[92mNo filters loaded.\033[0m")
        return 'Unknown', '17'  # Return default cat_id when no filters are loaded
    
    # Check if there are any .mp3 files in the directory
    if check_for_mp3_files(full_directory_path):
        print("\033[93mDirectory contains .mp3 files. Categorizing as Music/MP3.\033[0m")
        return 'Music/MP3', '22'  # Return the MP3 category directly

    matched_category = 'Unknown'
    matched_category_id = '17'  # Default to '17' if no match is found

    print(f"\033[33mFind the correct category\n\033[0m")  # Add 'f' for f-string
    # Iterate over top-level configurations to find a match
    for filter_key, filter_config in filters.items():        
        print(f"\033[95mChecking top-level filter: {filter_key}\033[0m")  # Add 'f' for f-string
        exclude_patterns = filter_config.get('patterns', {}).get('exclude_patterns', [])
        
        # Skip empty exclude patterns
        if exclude_patterns and any(re.search(pattern, directory_name, re.IGNORECASE) for pattern in exclude_patterns if pattern.strip()):
            continue  # Skip this filter

        initial_patterns = filter_config.get('patterns', {}).get('initial', [])
        
        if initial_patterns and any(re.search(pattern.replace('*', '.*'), directory_name, re.IGNORECASE) for pattern in initial_patterns):
            print(f"\033[92m\nMatched initial patterns for top-level filter: {filter_key}\n\033[0m")  # Add 'f' for f-string

            categories = filter_config.get('categories', [])
            for category_info in categories:
                category_name = category_info.get('name', 'Unknown')
                category_id = category_info.get('cat_id', 'Unknown')
                patterns = category_info.get('patterns', [])
                unwanted_patterns = category_info.get('exclude_patterns', [])

                # Skip empty unwanted patterns
                if unwanted_patterns and any(re.search(pattern, directory_name, re.IGNORECASE) for pattern in unwanted_patterns if pattern.strip()):
                    continue  # Skip this category if unwanted patterns matched

                if not patterns or any(re.search(pattern.replace('*', '.*'), directory_name, re.IGNORECASE) for pattern in patterns):
                    matched_category = category_name
                    matched_category_id = category_id
                    break  # Found a matching category, no need to check further categories in this filter

            if matched_category != 'Unknown':
                break  # Found a matching category, exit the loop

    # Check for a default category if nothing else matched
    if matched_category == 'Unknown':
        for filter_key, filter_config in filters.items():
            categories = filter_config.get('categories', [])
            for category_info in categories:
                if category_info.get('default', False):
                    print(f"\033[91mDirectory name matched default category: {category_info.get('name', 'Unknown')} (ID: {category_info.get('cat_id', 'Unknown')})\033[0m")  # Add 'f' for f-string
                    return category_info.get('name', 'Unknown'), category_info.get('cat_id', 'Unknown')

    print(f"\033[92mFound Category: {matched_category} (ID: {matched_category_id})\n\033[0m")  # Add 'f' for f-string
    return matched_category, matched_category_id
