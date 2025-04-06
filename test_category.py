import os
import re
import json
import sys
from configparser import ConfigParser

def load_config(config_file='config.ini'):
    """Load the configuration from the specified file."""
    config = ConfigParser()
    config.read(config_file)
    return config

def load_filters(filters_file='files/filters.json'):
    """Load the filters from the filters.json file."""
    with open(filters_file, 'r') as f:
        return json.load(f)

def determine_category(directory_name):
    """Determine the category of the content based on directory name using filters from filters.json."""
    filters = load_filters()
    config = load_config()  # Load configuration
    data_dir = config.get('Paths', 'DATADIR').strip()  # Get DATADIR from config
    full_directory_path = os.path.join(data_dir, directory_name)
    
    if not filters:
        print("\033[92mNo filters loaded.\033[0m")
        return 'Unknown', '17'  # Return default cat_id when no filters are loaded

    matched_category = 'Unknown'
    matched_category_id = '17'  # Default to '17' if no match is found

    print(f"\033[33mFind the correct category\n\033[0m")
    
    # Iterate over top-level configurations to find a match
    for filter_key, filter_config in filters.items():
        print(f"\033[95mChecking top-level filter: {filter_key}\033[0m")
        
        exclude_patterns = filter_config.get('patterns', {}).get('exclude_patterns', [])
        print(f"\033[96mExclude Patterns for {filter_key}: {exclude_patterns}\033[0m")
        
        # Check exclude patterns, skip if empty or blank
        if exclude_patterns and any(re.search(pattern, directory_name, re.IGNORECASE) for pattern in exclude_patterns if pattern.strip()):
            print(f"\033[91mDirectory {directory_name} excluded by pattern in {filter_key}.\033[0m")
            continue  # Skip this filter if any exclude pattern matches
        
        initial_patterns = filter_config.get('patterns', {}).get('initial', [])
        print(f"\033[96mInitial Patterns for {filter_key}: {initial_patterns}\033[0m")

        # Check initial patterns
        if initial_patterns and any(re.search(pattern.replace('*', '.*'), directory_name, re.IGNORECASE) for pattern in initial_patterns):
            print(f"\033[92mMatched initial patterns for top-level filter: {filter_key}\033[0m")

            categories = filter_config.get('categories', [])
            for category_info in categories:
                category_name = category_info.get('name', 'Unknown')
                category_id = category_info.get('cat_id', 'Unknown')
                patterns = category_info.get('patterns', [])
                unwanted_patterns = category_info.get('exclude_patterns', [])

                print(f"\033[96mChecking category: {category_name} (ID: {category_id})\033[0m")
                print(f"\033[96mCategory Patterns: {patterns}\033[0m")
                print(f"\033[96mCategory Exclude Patterns: {unwanted_patterns}\033[0m")

                # Check unwanted patterns for the category, skip if empty or blank
                if unwanted_patterns and any(re.search(pattern, directory_name, re.IGNORECASE) for pattern in unwanted_patterns if pattern.strip()):
                    print(f"\033[91mDirectory {directory_name} excluded by category pattern in {category_name}.\033[0m")
                    continue  # Skip this category if unwanted patterns matched

                # Check if the directory matches category patterns
                if not patterns or any(re.search(pattern.replace('*', '.*'), directory_name, re.IGNORECASE) for pattern in patterns):
                    matched_category = category_name
                    matched_category_id = category_id
                    print(f"\033[92mMatched category: {category_name} (ID: {category_id})\033[0m")
                    break  # Found a matching category, no need to check further categories in this filter

            if matched_category != 'Unknown':
                break  # Found a matching category, exit the loop

    # Check for a default category if nothing else matched
    if matched_category == 'Unknown':
        for filter_key, filter_config in filters.items():
            categories = filter_config.get('categories', [])
            for category_info in categories:
                if category_info.get('default', False):
                    print(f"\033[91mDirectory name matched default category: {category_info.get('name', 'Unknown')} (ID: {category_info.get('cat_id', 'Unknown')})\033[0m")
                    return category_info.get('name', 'Unknown'), category_info.get('cat_id', 'Unknown')

    print(f"\033[92mFound Category: {matched_category} (ID: {matched_category_id})\n\033[0m")
    return matched_category, matched_category_id

# Test with directory name as a command-line argument
if __name__ == "__main__":
    if len(sys.argv) > 1:
        directory_name = sys.argv[1]
    else:
        print("Usage: python3 script.py <directory_name>")
        sys.exit(1)

    determine_category(directory_name)
