import os
import shlex
import subprocess
import requests
from pathlib import Path
from utils.logging_utils import log_to_file
from utils.config_loader import ConfigLoader
from utils.fastresume_utils import add_fastresume
import configparser
import shutil

# Load configuration
config = ConfigLoader().get_config()

TMP_DIR = os.path.join(config.get('Paths', 'TMP_DIR'), str(os.getpid()))
WATCHFOLDER = config.get('Paths', 'WATCHFOLDER')
PREPENDNAME = config.get('Settings', 'PREPENDNAME')

# Ensure TMP_DIR exists
os.makedirs(TMP_DIR, exist_ok=True)

def create_torrent(directory, temp_dir):
    """Create a torrent file from the given directory using torf-cli."""
    try:
        edit_torrent = config.getboolean('Torrent', 'EDIT_TORRENT')
        etorf = config.get('Torrent', 'ETORF')
        ecomment = config.get('Torrent', 'ECOMMENT')
        esource = config.get('Torrent', 'ESOURCE')
        creator = config.get('Torrent', 'CREATOR')
        announceurl = config.get('Torrent', 'ANNOUNCEURL')
        etorrentpath = config.get('Torrent', 'ETORFPATH')
    except (configparser.NoOptionError, configparser.NoSectionError) as e:
        print(f"Config error: {e}")
        return None

    directory_path = Path(directory)
    temp_dir_path = Path(temp_dir)
    torrent_file = temp_dir_path / f"{directory_path.name}.torrent"
    etorrent_file_path = Path(etorrentpath) / f"{directory_path.name}.torrent"

    if etorrentpath:  # Proceed only if ETORFPATH is not empty
        etorrent_file_path = Path(etorrentpath) / f"{directory_path.name}.torrent"
    else:
        print("ETORFPATH is not configured; skipping edit and will create a new torrent.")
        etorrent_file_path = None

    piece_size = calculate_piece_size(directory)

    if edit_torrent and etorrent_file_path and etorrent_file_path.exists():
        torf_cmd = (
            f"{shlex.quote(etorf)} "
            f"-i {shlex.quote(str(torrent_file))} "
            f"--notracker --nomagnet "
            f"--comment {shlex.quote(ecomment)} "
            f"--yes --source {shlex.quote(esource)} "
            f"--creator {shlex.quote(creator)} "
            f"--tracker {shlex.quote(announceurl)} "
            f"--out {shlex.quote(str(torrent_file))}"
        )
        print(f"### Found existing torrent. {torrent_file}")
    else:
        torf_cmd = (
            f"{shlex.quote(etorf)} "
            f"{shlex.quote(str(directory_path))} "
            f"--max-piece-size {piece_size} "
            f"--nomagnet --xseed "
            f"--comment {shlex.quote(ecomment)} "
            f"--yes --source {shlex.quote(esource)} "
            f"--creator {shlex.quote(creator)} "
            f"--tracker {shlex.quote(announceurl)} "
            f"--out {shlex.quote(str(torrent_file))}"
        )
        print(f"\033[36mCreate torrent file.. {torrent_file}\n\033[0m")

    log_to_file(temp_dir_path / 'create_torrent_cmd.txt', torf_cmd)
    
    try:
        result = subprocess.run(torf_cmd, shell=True, text=True, capture_output=True)
        
        log_to_file(temp_dir_path / 'create_torrent_output.log', result.stdout)
        log_to_file(temp_dir_path / 'create_torrent_error.log', result.stderr)
        
        if result.returncode != 0:
            raise RuntimeError(f"torf command failed with exit code {result.returncode}")
        
        print(f"\033[92mTorrent created: {torrent_file}\n\033[0m")
        return str(torrent_file), piece_size  # Return the path to the torrent file as a string
    except Exception as e:
        log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
        print(f"Error creating torrent: {e}")
        return None, None

def calculate_piece_size(directory):
    """Calculate the appropriate piece size for the torrent based on directory size."""
    total_size = sum(
        os.path.getsize(os.path.join(root, file))
        for root, _, files in os.walk(directory)
        for file in files
    )

    MBs = total_size // (1024 * 1024)

    if MBs > 484352:
        PIECES = 24
    elif MBs > 194560:
        PIECES = 24
    elif MBs > 73728:
        PIECES = 23
    elif MBs > 16384:
        PIECES = 22
    elif MBs > 8192:
        PIECES = 21
    elif MBs > 4096:
        PIECES = 20
    elif MBs > 2048:
        PIECES = 19
    elif MBs > 1024:
        PIECES = 18
    elif MBs > 512:
        PIECES = 17
    elif MBs > 256:
        PIECES = 16
    else:
        PIECES = 15

    return PIECES


def download_duplicate_torrent(url, cookies, release_name, is_dupe=False, dupe_id=None):
    """Download a torrent file, distinguishing between duplicate and regular torrents."""
    try:
        # Determine the temporary file path with appropriate naming
        temp_torrent_path = os.path.join(TMP_DIR, f'{dupe_id}_{release_name}.torrent') if is_dupe and dupe_id else os.path.join(TMP_DIR, f'{release_name}.torrent')

        # Download the torrent content
        response = requests.get(url, cookies=cookies, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()  # Raise an error for bad responses
        log_to_file(os.path.join(TMP_DIR, 'response_debug.log'), f"Response status: {response.status_code}\nResponse content: {response.text}")

        # Write the torrent content to the temporary file
        with open(temp_torrent_path, 'wb') as f:
            f.write(response.content)

        # Choose the appropriate log file
        log_file = 'dupe_download.log' if is_dupe else 'torrent_download.log'
        
        # Log the successful download
        log_to_file(os.path.join(TMP_DIR, log_file), f"Torrent downloaded successfully: {temp_torrent_path}")
        print(f"\033[92mTorrent downloaded successfully: {temp_torrent_path}\n\033[0m")
        
        # Check if fast resume should be added
        add_fastresume_flag = config.getboolean('Settings', 'ADDFASTRESUME')
        if add_fastresume_flag:
            # Get the data directory from configuration
            download_dir = config.get('Paths', 'DATADIR')  # Ensure this path is correct
            
            # Prepare the fast resume output file path
            fastresume_output_path = os.path.join(TMP_DIR, f'dc.{release_name}.torrent')
            
            # Add fast resume data
            add_fastresume(temp_torrent_path, download_dir, fastresume_output_path)
            
            # Check if the fast resume file exists and move it
            if os.path.exists(fastresume_output_path):
                final_torrent_path = os.path.join(WATCHFOLDER, f'{PREPENDNAME}{release_name}.torrent')
                
                # Use copyfile and remove instead of rename
                shutil.copyfile(fastresume_output_path, final_torrent_path)
                os.remove(fastresume_output_path)
                
                print(f"\033[92mTorrent copied to watch folder: {final_torrent_path}\n\033[0m")
            else:
                print(f"\033[91mFast resume output file not found: {fastresume_output_path}\033[0m")
        else:
            final_torrent_path = os.path.join(WATCHFOLDER, f'{PREPENDNAME}{release_name}.torrent')
            
            # Use copyfile and remove instead of rename
            shutil.copyfile(temp_torrent_path, final_torrent_path)
            os.remove(temp_torrent_path)
            
            print(f"\033[92mTorrent copied to watch folder: {final_torrent_path}\n\033[0m")

    except requests.RequestException as e:
        # Log any request exceptions
        log_to_file(os.path.join(TMP_DIR, 'dupe_download_error.log' if is_dupe else 'torrent_download_error.log'), f"Failed to download torrent: {str(e)}")
        print(f"\033[91mFailed to download torrent: {str(e)}\033[0m")

    except Exception as e:
        # General exception logging
        log_to_file(os.path.join(TMP_DIR, 'dupe_general_error.log' if is_dupe else 'torrent_general_error.log'), f"An error occurred: {str(e)}")
        print(f"\033[91mAn error occurred: {str(e)}\033[0m")





def upload_torrent(torrent_file, template_file, cookies, category_id, imdb_id, mediainfo_text):
    """
    Uploads a torrent file to the specified site with the required details.

    Args:
        torrent_file (str): Path to the .torrent file.
        template_file (str): Path to the NFO template file.
        cookies (dict): Cookies to be used in the request.
        category_id (int): The ID of the category of the torrent.
        imdb_id (str): The IMDB ID associated with the torrent.
        mediainfo_text (str): The mediainfo text to be included in the upload.

    Returns:
        None
    """
    # Log torrent file path to ensure it's correct
    #print(f"Torrent file path: {torrent_file}")
    
    upload_url = f"{config.get('Website', 'SITEURL')}/api/v1/torrents/upload"
    user_agent = config.get('Network', 'UserAgent', fallback='Mozilla/5.0')
    
    # Read the content of the template file
    with open(template_file, 'r', encoding='utf-8') as file:
        nfo_content = file.read()
    
    # Open the torrent file in binary mode
    with open(torrent_file, 'rb') as torrent_file_obj:
        files = {
            'file': (os.path.basename(torrent_file), torrent_file_obj, 'application/x-bittorrent')
        }
        
        data = {
            'category': category_id,
            'imdbId': imdb_id,
            'reqid': 0,
            'section': 'new',
            'frileech': 1,
            'anonymousUpload': 1,
            'p2p': 0,
            'nfo': nfo_content,
            'mediainfo': mediainfo_text,
        }
        
        # Log request details for debugging
        log_to_file(os.path.join(TMP_DIR, 'upload_request.log'), f"Uploading to URL: {upload_url}")
        log_to_file(os.path.join(TMP_DIR, 'upload_request.log'), f"Headers: {{'User-Agent': '{user_agent}', 'Expect': ''}}")
        log_to_file(os.path.join(TMP_DIR, 'upload_request.log'), f"Cookies: {cookies}")
        log_to_file(os.path.join(TMP_DIR, 'upload_request.log'), f"Files: {files}")
        log_to_file(os.path.join(TMP_DIR, 'upload_request.log'), f"Data: {data}")

        try:
            response = requests.post(
                upload_url,
                headers={'User-Agent': user_agent, 'Expect': ''},
                cookies=cookies,
                files=files,
                data=data,
                verify=False
            )
        except requests.RequestException as e:
            log_to_file(os.path.join(TMP_DIR, 'upload_response.log'), f"Request exception: {e}")
            print(f"Request exception: {e}")
            return

        # Log the upload response
        log_to_file(os.path.join(TMP_DIR, 'upload_response.log'), f"Upload response status: {response.status_code}\n{response.text}")
        
        if response.status_code == 200:
            print(f"\033[92mTorrent uploaded successfully.\n\033[0m")
            response_json = response.json()
            torrent_id = response_json.get('id')
            torrent_name = response_json.get('name')
            
            # Download the torrent file using the ID from the response
            dupe_torrent_url = f"{config.get('Website', 'SITEURL')}/api/v1/torrents/download/{torrent_id}"
            download_duplicate_torrent(dupe_torrent_url, cookies, torrent_name, torrent_id)
        else:
            print(f"Failed to upload torrent. Status code: {response.status_code}\nResponse: {response.text}")
