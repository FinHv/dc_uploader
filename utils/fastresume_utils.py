import os
import rfr
from utils.art_utils import ascii_art_header

def add_fastresume(torrent_file, download_dir, output_file):
    """Add fast resume to the torrent using the rfr Python module."""
    #print(f"\033[94mAdding fast resume information...\033[0m")
    #print(f"Torrent file: {torrent_file}")
    #print(f"Download directory: {download_dir}")
    #print(f"Output file: {output_file}")
    print(ascii_art_header("Fastresume"))

    try:
        # Check if the torrent file exists
        if not os.path.isfile(torrent_file):
            raise FileNotFoundError(f"Torrent file not found: {torrent_file}")

        # Initialize FastTorrent object
        tor = rfr.FastTorrent(torrent_file, download_dir)
        
        # Generate fast resume data
        tor.do_resume()
        
        # Save the resulting torrent to a file
        tor.save_to_file(output_file)
        
        if os.path.exists(output_file):
            print(f"\033[92mFast resume added successfully: {output_file}\n\033[0m")
        else:
            raise FileNotFoundError(f"Fast resume output file not found: {output_file}")
    except FileNotFoundError as e:
        print(f"\033[91mFile not found: {str(e)}\033[0m")
    except Exception as e:
        print(f"\033[91mFailed to add fast resume: {str(e)}\033[0m")
