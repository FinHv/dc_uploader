import json
import os
import shutil

import requests

from utils.config_loader import ConfigLoader
from utils.logging_utils import log_to_file
from utils.torrent_utils import download_duplicate_torrent

# Load configuration
config = ConfigLoader().get_config()
TMP_DIR = os.path.join(config.get('Paths', 'TMP_DIR'), str(os.getpid()))

# Ensure TMP_DIR exists
os.makedirs(TMP_DIR, exist_ok=True)

def check_and_download_dupe(release_name, cookies):
    """Check for duplicate torrent and download it if found, based on configuration."""
    dupe_check_flag = config.getboolean('Settings', 'DUPECHECK')
    dupe_dl_flag = config.getboolean('Settings', 'DUPEDL')

    # Get the watch folder from the configuration
    watch_folder = config.get('Paths', 'WATCHFOLDER')

    if not dupe_check_flag:
        print(f"\033[93mDuplicate check is disabled in the configuration.\033[0m")
        return False

    search_url = f"{config.get('Website', 'SITEURL')}/api/v1/torrents_exact_search?searchText={release_name}"
    try:
        print(f"\033[33mChecking for dupe: {release_name}\n\033[0m")
        response = requests.get(search_url, cookies=cookies, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()

        # Log the response
        log_to_file(os.path.join(TMP_DIR, 'dupe_check_response.log'), response.text)

        # Check if the response is empty
        if not response.text.strip():
            print(f"\033[91mDid not found a dupe for: {release_name}\n\033[0m")
            log_to_file(os.path.join(TMP_DIR, 'dupe_empty_response.log'), f"Empty response received for: {release_name}")
            return False

        # Parse the JSON response
        try:
            torrents = json.loads(response.text)
        except json.JSONDecodeError as e:
            print(f"\033[91mFailed to decode JSON response: {str(e)}\033[0m")
            log_to_file(os.path.join(TMP_DIR, 'dupe_json_decode_error.log'), f"Failed to decode JSON response: {str(e)}")
            return False

        if not isinstance(torrents, list):
            print(f"\033[91mUnexpected response format for: {release_name}\033[0m")
            log_to_file(os.path.join(TMP_DIR, 'dupe_unexpected_format.log'), f"Unexpected response format for: {release_name}")
            return False

        for torrent in torrents:
            if torrent['name'] == release_name:
                torrent_id = torrent['id']
                dupe_torrent_url = f"{config.get('Website', 'SITEURL')}/api/v1/torrents/download/{torrent_id}"
                
                # Log and print the duplicate detection
                log_to_file(os.path.join(TMP_DIR, 'dupe_detected.log'), f"Duplicate found: {release_name} (ID: {torrent_id})")
                print(f"\033[92mDuplicate found: {release_name}.\033[0m")

                # If DUPECHECK is true and DUPEDL is false, exit the script after checking for duplicates
                if not dupe_dl_flag:
                    print(f"\033[93mDuplicate download is disabled in the configuration. Exiting.\033[0m")
                    return True  # Indicate that a duplicate was found but not downloaded

                # Download the duplicate torrent and get its file path
                torrent_file_path = download_duplicate_torrent(dupe_torrent_url, cookies, release_name, dupe_id=torrent_id)

                # Copy the downloaded torrent to the watch folder
                destination_path = os.path.join(watch_folder, os.path.basename(torrent_file_path))
                shutil.copyfile(torrent_file_path, destination_path)

                print(f"\033[92mDownloaded torrent copied to watch folder: {destination_path}\033[0m")
                return True  # Indicate that a duplicate was found and handled
        
        # If no duplicate was found
        print(f"\033[91mNo duplicate found for: {release_name}\033[0m")
        log_to_file(os.path.join(TMP_DIR, 'dupe_not_found.log'), f"No duplicate found for: {release_name}")
        return False

    except requests.RequestException as e:
        # Log any request exceptions
        log_to_file(os.path.join(TMP_DIR, 'dupe_check_error.log'), f"Failed to check for duplicate: {str(e)}")
        print(f"\033[91mFailed to check for duplicate: {str(e)}\033[0m")
        return False
