import os
import platform
import shlex
import subprocess

import requests
from pathlib import Path
from utils.logging_utils import log_to_file
from utils.config_loader import ConfigLoader
from utils.fastresume_utils import add_fastresume
from torf import Torrent, ReadError, BdecodeError, MetainfoError
import re
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
    cli_ui.info_progress(f"Torf hashing... {speed_str} | ETA: {eta}", int(percentage_done), 100)

def create_torrent(directory, temp_dir):
    """Create a torrent file from the given directory using torf-cli."""
    try:
        edit_torrent = config.getboolean('Torrent', 'EDIT_TORRENT')
        ecomment = config.get('Torrent', 'ECOMMENT').strip()
        esource = config.get('Torrent', 'ESOURCE').strip()
        creator = config.get('Torrent', 'CREATOR').strip()
        announceurl = config.get('Torrent', 'ANNOUNCEURL').strip()
        etorrentpath = config.get('Torrent', 'SOURCEFOLDER').strip().rstrip('/')
        hasher = config.get('Torrent', 'HASHER').strip()
    except (configparser.NoOptionError, configparser.NoSectionError) as e:
        print(f"Config error: {e}")
        return None

    directory_path = Path(directory)
    temp_dir_path = Path(temp_dir)
    output_torrent = f"{shlex.quote(str(temp_dir_path / f"{directory_path.name}.torrent"))}"

    # Proceed only if SOURCEFOLDER is set
    if etorrentpath:
        etorrent_file_path = Path(etorrentpath) / f"{directory_path.name}.torrent"
    else:
        print("SOURCEFOLDER is not configured; not reusing existing torrent. New torrent will be generated.")
        etorrent_file_path = None

    piece_size = calculate_piece_size(directory)
    max_piece_size_bytes = piece_size * 1024 * 1024
    if edit_torrent and etorrent_file_path and etorrent_file_path.exists():
        # Existing torrent successfully found, and torrent reuse is desired
        try:
            reused_torrent = Torrent.read(f"{shlex.quote(str(etorrent_file_path))}")
        except (ReadError, BdecodeError, MetainfoError):
            print("No existing .torrent found. New torrent will be generated.")
        except Exception as e:
            # Catch the rest
            log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
            print(f"Error reusing torrent: {e}")
            return None, None
        else:
            print(f"### Found existing torrent. {output_torrent}")
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
            Torrent.copy(reused_torrent).write(output_torrent, overwrite=True)
    else:
        try:
            if hasher == 'torf':
                new_torrent = Torrent(path=str(directory_path),
                                      name=directory_path.name,
                                      trackers=[announceurl],
                                      source=esource,
                                      created_by=creator,
                                      comment=ecomment,
                                      randomize_infohash=True,
                                      private=True,
                                      piece_size_max=max_piece_size_bytes)
                if new_torrent.generate(callback=torf_cb, interval=5):
                    new_torrent.write(output_torrent, overwrite=True)
                    log_to_file(temp_dir_path / 'create_torrent_output.log',
                                "New torrent successfully generated. Validating now")
                    print("New torrent successfully generated. Validating now")
                    try:
                        Torrent.read(output_torrent).validate()
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
            elif hasher == 'mkbrr':
                platform_type = platform.machine()
                mkbrr_path = 'bin/mkbrr/linux/'
                if platform_type == 'amd64':
                    mkbrr_path += 'amd64/mkbrr'
                elif platform_type == 'x86_64':
                    mkbrr_path += 'x86_64/mkbrr'
                elif platform_type == 'aarch64' or platform_type == 'arm64' or 'armv8' in platform_type:
                    mkbrr_path += 'arm64/mkbrr'
                elif "armv6" in platform_type:
                    mkbrr_path += 'armv6/mkbrr'
                elif "armv7" in platform_type:
                    mkbrr_path += 'arm/mkbrr'
                else:
                    log_to_file(temp_dir_path / 'create_torrent_error.log',
                                f"Unsupported platform: {platform_type}")
                    print(f"Unsupported platform: {platform_type}")
                    return None, None

                # Ensure mkbrr is executable for both owner and group
                os.chmod(mkbrr_path, 0o775)

                if piece_size < 16:
                    # Mkbrr only supports a minimum piece length of 16. If it's lower than 16, set to 16.
                    max_piece_size_bytes = 16 * 1024 * 1024

                # Largest power of 2 that's less than or equal to max piece size in bytes
                import math
                power = min(27, max(16, math.floor(math.log2(max_piece_size_bytes))))
                print(
                    f"[yellow]Setting mkbrr piece length to 2^{power} ({(2 ** power) / (1024 * 1024):.2f} MiB)")
                cmd = [mkbrr_path,
                       "create",
                       f"{shlex.quote(str(directory_path))}",
                       f'-t {announceurl}',
                       '-e',
                       f'-l {str(power)}',
                       f'-o {output_torrent}',
                       f'-s {esource}',
                       f'-c {ecomment}']

                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

                total_pieces = 100  # Default to 100% for scaling progress
                pieces_done = 0
                mkbrr_start_time = time.time()
                torrent_written = False

                from rich.console import Console
                console = Console()
                for line in process.stdout:
                    line = line.strip()

                    # Detect hashing progress, speed, and percentage
                    match = re.search(r"Hashing pieces.*?\[(\d+(?:\.\d+)? (?:MB|MiB)/s)\]\s+(\d+)%", line)
                    if match:
                        speed = match.group(1)  # Extract speed (e.g., "12734.21 MB/s")
                        pieces_done = int(match.group(2))  # Extract percentage (e.g., "60")

                        # Estimate ETA (Time Remaining)
                        elapsed_time = time.time() - mkbrr_start_time

                        if pieces_done > 0:
                            estimated_total_time = elapsed_time / (pieces_done / 100)
                            eta_seconds = max(0, estimated_total_time - elapsed_time)
                            eta = time.strftime("%M:%S", time.gmtime(eta_seconds))
                        else:
                            eta = "--:--"  # Placeholder if we can't estimate yet

                        cli_ui.info_progress(f"mkbrr hashing... {speed} | ETA: {eta}", pieces_done, total_pieces)

                    # Detect final output line
                    if "Wrote" in line and ".torrent" in line:
                        console.print(f"[bold cyan]{line}")  # Print the final torrent file creation message
                        torrent_written = True

                # Wait for the process to finish
                result = process.wait()

                # Verify the torrent was actually created
                if result != 0:
                    console.print(f"[bold red]mkbrr exited with non-zero status code: {result}")
                    raise RuntimeError(f"mkbrr exited with status code {result}")

                if not torrent_written or not os.path.exists(output_torrent):
                    console.print("[bold red]mkbrr did not create a torrent file!")
                    raise FileNotFoundError(f"Expected torrent file {output_torrent} was not created")

                try:
                    test_torrent = Torrent.read(output_torrent)
                    if not test_torrent.metainfo.get('info', {}).get('pieces'):
                        console.print("[bold red]Generated torrent file appears to be invalid (missing pieces)")
                        raise ValueError("Generated torrent is missing pieces hash")
                except Exception as e:
                    log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
                    print(f"Error creating torrent: {e}")
                    return None, None
            else:
                log_to_file(temp_dir_path / 'create_torrent_error.log',
                            f"Unknown hasher")
                print(f"Unknown hasher")
                return None, None
        except Exception as e:
                log_to_file(temp_dir_path / 'create_torrent_error.log', str(e))
                print(f"Error generating torrent: {e}")
                return None, None
    try:
        print(f"\033[92mTorrent to be uploaded has been created: {output_torrent}\n\033[0m")
        return output_torrent, piece_size  # Return the path to the torrent file as a string
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

    mb = total_size // (1024 * 1024)

    if mb > 484352:
        pieces = 24
    elif mb > 194560:
        pieces = 24
    elif mb > 73728:
        pieces = 23
    elif mb > 16384:
        pieces = 22
    elif mb > 8192:
        pieces = 21
    elif mb > 4096:
        pieces = 20
    elif mb > 2048:
        pieces = 19
    elif mb > 1024:
        pieces = 18
    elif mb > 512:
        pieces = 17
    elif mb > 256:
        pieces = 16
    else:
        pieces = 15

    return pieces


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
            'frileech': int(f"{config.get('UploadForm', 'FREELEECH')}"),
            'anonymousUpload': int(f"{config.get('UploadForm', 'ANONYMOUS')}"),
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
