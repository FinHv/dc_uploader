import os
import shlex

import requests
from pathlib import Path
from utils.logging_utils import log_to_file
from utils.config_loader import ConfigLoader
from utils.fastresume_utils import add_fastresume
from torf import Torrent
import time
import configparser
import shutil
import cli_ui

# Load configuration
config = ConfigLoader().get_config()

TMP_DIR = os.path.join(config.get('Paths', 'TMP_DIR'), str(os.getpid()))
WATCHFOLDER = config.get('Paths', 'WATCHFOLDER')
PREPENDNAME = config.get('Settings', 'PREPENDNAME')

# Ensure TMP_DIR exists
os.makedirs(TMP_DIR, exist_ok=True)
torf_start_time = time.time()

def torf_cb(torrent, filepath, pieces_done, pieces_total):
    global torf_start_time

    if pieces_done == 0:
        torf_start_time = time.time()  # Reset start time when hashing starts

    elapsed_time = time.time() - torf_start_time

    # Calculate percentage done
    if pieces_total > 0:
        percentage_done = (pieces_done / pieces_total) * 100
    else:
        percentage_done = 0

    # Estimate ETA (if at least one piece is done)
    if pieces_done > 0:
        estimated_total_time = elapsed_time / (pieces_done / pieces_total)
        eta_seconds = max(0, estimated_total_time - elapsed_time)
        eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
    else:
        eta = "--:--"

    # Calculate hashing speed (MB/s)
    if elapsed_time > 0 and pieces_done > 0:
        piece_size = torrent.piece_size / (1024 * 1024)
        speed = (pieces_done * piece_size) / elapsed_time
        speed_str = f"{speed:.2f} MB/s"
    else:
        speed_str = "-- MB/s"

    # Display progress with percentage, speed, and ETA
    cli_ui.info_progress(f"Hashing... {speed_str} | ETA: {eta}", int(percentage_done), 100)

def create_torrent(directory, temp_dir):
    """Create a torrent file from the given directory using torf-cli."""
    try:
        edit_torrent = config.getboolean('Torrent', 'EDIT_TORRENT')
        ecomment = config.get('Torrent', 'ECOMMENT')
        esource = config.get('Torrent', 'ESOURCE')
        creator = config.get('Torrent', 'CREATOR')
        announceurl = config.get('Torrent', 'ANNOUNCEURL')
        etorrentpath = config.get('Torrent', 'SOURCEPATH')
    except (configparser.NoOptionError, configparser.NoSectionError) as e:
        print(f"Config error: {e}")
        return None

    directory_path = Path(directory)
    temp_dir_path = Path(temp_dir)
    torrent_file = temp_dir_path / f"{directory_path.name}.torrent"

    # Proceed only if SOURCEPATH is not empty
    if etorrentpath:
        etorrent_file_path = Path(etorrentpath) / f"{directory_path.name}.torrent"
    else:
        print("SOURCEPATH is not configured; not reusing existing torrent. New torrent will be generated.")
        etorrent_file_path = None

    piece_size = calculate_piece_size(directory)
    if edit_torrent and etorrent_file_path and etorrent_file_path.exists():
        # Existing torrent successfully found, and torrent reuse is desired
        try:
            reused_torrent = Torrent.read(f"{shlex.quote(str(etorrent_file_path))}")
        except Exception as e:
            log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
            print(f"Error reusing torrent: {e}")
            return None, None
        else:
            print(f"### Found existing torrent. {torrent_file}")
            # Now edit the torrent as an object
            reused_torrent.trackers = [announceurl]
            reused_torrent.comment = ecomment
            reused_torrent.created_by = creator

            info_dict = reused_torrent.metainfo['info']
            valid_keys = ['name', 'piece length', 'pieces', 'private', 'source']

            # Add the correct key based on single vs multi file torrent
            if 'files' in info_dict:
                valid_keys.append('files')
            elif 'length' in info_dict:
                valid_keys.append('length')

            # Remove everything not in the whitelist
            for each in list(info_dict):
                if each not in valid_keys:
                    info_dict.pop(each, None)
            for each in list(reused_torrent.metainfo):
                if each not in ('announce', 'comment', 'creation date', 'created by', 'encoding', 'info'):
                    reused_torrent.metainfo.pop(each, None)

            reused_torrent.source = f"{shlex.quote(esource)}"
            reused_torrent.private = True
            Torrent.copy(reused_torrent).write(f"{shlex.quote(str(torrent_file))}", overwrite=True)
    else:
        try:
            new_torrent = Torrent(path=str(directory_path),
                                  name=directory_path.name,
                                  trackers=[announceurl],
                                  source=esource,
                                  created_by=creator,
                                  comment=ecomment,
                                  randomize_infohash=True,
                                  private=True,
                                  piece_size_max=piece_size * 1048576)
            if new_torrent.generate(callback=torf_cb, interval=5):
                new_torrent.write(f"{shlex.quote(str(torrent_file))}", overwrite=True)
                log_to_file(temp_dir_path / 'create_torrent_output.log',
                            "New torrent successfully generated. Validating now")
                print("New torrent successfully generated. Validating now")
                try:
                    Torrent.read(f"{shlex.quote(str(torrent_file))}").validate()
                    new_torrent.verify_filesize(directory_path)
                    log_to_file(temp_dir_path / 'create_torrent_output.log', "Torrent file successfully validated")
                    print("Torrent file successfully validated")
                except Exception as e:
                    log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
                    print(f"Error, generated torrent is not valid: {e}")
                    return None, None
            else:
                log_to_file(temp_dir_path / 'create_torrent_error.log', f"Failed to hash all pieces during torrent generation")
                print(f"Failed to hash all pieces during torrent generation")
                return None, None
        except Exception as e:
                log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
                print(f"Error generating torrent: {e}")
                return None, None
    try:
        print(f"\033[92mTorrent to be uploaded has been created: {torrent_file}\n\033[0m")
        return str(torrent_file), piece_size  # Return the path to the torrent file as a string
    except Exception as e:
        log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
        print(f"Error creating torrent: {e}")
        return None, None

def calculate_size(directory):
    """Calculate the directory size."""
    total_size = sum(
        os.path.getsize(os.path.join(root, file))
        for root, _, files in os.walk(directory)
        for file in files
    )

    return total_size

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
            'frileech': int(f"{config.get('UploadForm', 'freeleech')}"),
            'anonymousUpload': int(f"{config.get('UploadForm', 'anonymousUpload')}"),
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
