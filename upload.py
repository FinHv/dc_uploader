import sys
import os
import re
import time
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from utils.status_utils import create_status_folder, remove_status_folder, update_status
from utils.config_loader import ConfigLoader
from utils.torrent_utils import create_torrent, upload_torrent, download_duplicate_torrent
from utils.directory_utils import create_process_directory
from utils.logging_utils import log_to_file, log_upload_details
from utils.dupe_utils import check_and_download_dupe
from utils.login_utils import login
from utils.category_utils import determine_category
from utils.screenshot_utils import generate_screenshots
from utils.template_utils import prepare_template
from utils.mediainfo_utils import generate_mediainfo
from utils.filters_utils import load_filters_with_path
from utils.imdb_utils import get_imdb_info, extract_imdb_link_from_nfo, extract_movie_details, extract_tv_show_details, get_imdb_tv_info
from utils.image_utils import upload_images
from utils.nfo_utils import process_nfo
from utils.art_utils import ascii_art_header
from utils.database_utils import insert_upload, update_upload_status
from utils.gameinfo_utils import fetch_game_info, extract_game_name

class CustomOutput:
    def __init__(self, original_stdout, db_path="data/terminal_output.db"):
        self.original_stdout = original_stdout
        self.db_path = db_path
        self.ensure_db_initialized()

    def ensure_db_initialized(self):
        """Initialize the SQLite database and the logs table if they don't exist."""
        # Ensure the database directory exists
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        # Connect to the database and ensure the table exists
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS terminal_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                source TEXT,  -- Optional, can be used to differentiate uploaders
                log_line TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def write(self, message):
        """Write to terminal and store message in the database."""
        # Write to terminal as normal
        self.original_stdout.write(message)

        # Log the message to the database
        self.log_to_db(message)

    def log_to_db(self, message):
        """Insert the log message into the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Insert the message into the logs table with the current timestamp
        c.execute('''
            INSERT INTO terminal_logs (log_line)
            VALUES (?)
        ''', (message,))
        
        conn.commit()
        conn.close()

    def flush(self):
        """Flush the original stdout."""
        self.original_stdout.flush()

# Replace sys.stdout with CustomOutput
sys.stdout = CustomOutput(sys.stdout)

def log(message, file_path):
    """Utility function to log messages to a file and print to the console."""
    #print(message)
    log_to_file(file_path, message)

def calculate_directory_size(directory):
    """Calculate the total size of files in a directory, including handling soft links."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.islink(fp):
                # If it's a symlink, follow the link and add its real size
                real_path = os.path.realpath(fp)
                total_size += os.path.getsize(real_path)
            else:
                # If it's a real file, just add its size
                total_size += os.path.getsize(fp)
    return round(total_size / (1024 * 1024), 2)  # Size in MB

def find_nfo_file(directory):
    """Find the .nfo file in the directory."""
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.nfo'):
                return os.path.join(root, file)
    return None

def cleanup_tmp_dir(directory, cleanup_enabled):
    """Clean up temporary directory if cleanup is enabled."""
    if cleanup_enabled:
        try:
            if directory.exists() and directory.is_dir():
                shutil.rmtree(directory)
                print(f"Cleaned up temporary directory: {directory}")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")


def main():
    """Main function to run the script."""

    # Load configuration
    config = ConfigLoader().get_config()
    TMP_DIR = Path(config.get('Paths', 'TMP_DIR')) / str(os.getpid())
    TEMPLATE_PATH = Path(config.get('Paths', 'TEMPLATE_PATH'))
    upload_log_path = Path(config.get('Paths', 'UPLOADLOG'))
    
    # Ensure TMP_DIR exists
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    log_file_path = TMP_DIR / 'main.log'

    # Ensure upload.log is created
    try:
        upload_log_path.touch(exist_ok=True)  # Create the file if it does not exist
        #print(f"Upload log created at: {upload_log_path}")
    except Exception as e:
        print(f"Error creating upload log: {str(e)}")
        return

    if len(sys.argv) > 1:
        directory_name = sys.argv[1]
    else:
        log("No directory name provided.", log_file_path)
        return

    print(ascii_art_header("Header"))
    print("\033[0m\033[94mStarting upload script...\n\033[0m")

    base_dir = Path(config.get('Paths', 'DATADIR'))
    directory = base_dir / directory_name

    if not directory.exists():
        log(f"The provided directory does not exist: {directory}", log_file_path)
        print(f"\033[0m\033[91mDirectory does not exist: {directory}\n\033[0m")
        return

    update_status(directory, 'uploading')

    # Initialize upload details dictionary
    upload_details = {
        "name": directory_name,
        "path": str(directory),
        "size": None,
        "category": None,
        "piece_size": None,
        "piece_size_bytes": None,
        "etor_started": None,
        "torrent_file": None,
        "etor_completed": None,
        "nfo": None
    }

    # Calculate directory size and check for NFO file
    upload_details['size'] = f"{calculate_directory_size(directory)} MB"
    upload_details['nfo'] = find_nfo_file(directory) or "NFO file not found"

    # Check if settings are enabled 
    screenshots_enabled = config.getboolean('Settings', 'SCREENSHOTS')
    rar2fs_screenshots_enabled = config.getboolean('Settings', 'RAR2FS_SCREENSHOTS')
    mediainfo_enabled = config.getboolean('Settings', 'MEDIAINFO')
    dupecheck_enabled = config.getboolean('Settings', 'DUPECHECK')
    dupedl_enabled = config.getboolean('Settings', 'DUPEDL')
    fast_resume = config.getboolean('Settings', 'ADDFASTRESUME')
    imdb_enabled = config.getboolean('Settings', 'IMDB')
    image_upload_enabled = config.getboolean('Settings', 'IMAGE_UPLOAD')
    gameinfo_enabled = config.getboolean('Settings', 'GAME_INFO')
    cleanup_enabled = config.getboolean('Settings', 'CLEANUP') 
    filters_path = config.get('Paths', 'FILTERS') 
    upload_log = config.get('Paths', 'UPLOADLOG') 

    screenshot_categories = [int(cat.strip()) for cat in config.get('Settings', 'SCREENSHOT_CATEGORIES').split(',')]
    rar2fs_categories = [int(cat.strip()) for cat in config.get('Settings', 'RAR2FS_CATEGORIES').split(',')]
    mediainfo_categories = [int(cat.strip()) for cat in config.get('Settings', 'MEDIAINFO_CATEGORIES').split(',')]
    imdb_movie_categories = [int(cat.strip()) for cat in config.get('Settings', 'IMDB_MOVIE_CATEGORIES').split(',')]
    imdb_tv_categories = [int(cat.strip()) for cat in config.get('Settings', 'IMDB_TV_CATEGORIES').split(',')]
    game_categories = [int(cat.strip()) for cat in config.get('Settings', 'GAME_CATEGORIES').split(',')]

    # Print settings status
    print()
    print(f"\033[31m################ Settings ################\n\033[0m")
    print(f"\033[32mScreenshots enabled: {screenshots_enabled}\033[0m")
    print(f"\033[32mRAR2FS enabled: {rar2fs_screenshots_enabled}\033[0m")
    print(f"\033[32mMediainfo enabled: {mediainfo_enabled}\033[0m")
    print(f"\033[32mDupecheck enabled: {dupecheck_enabled}\033[0m")
    print(f"\033[32mDupedownload enabled: {dupedl_enabled}\033[0m")
    print(f"\033[32mFastresume enabled: {fast_resume}\033[0m")
    print(f"\033[32mIMDB enabled: {imdb_enabled}\033[0m")
    print(f"\033[32mGameinfo enabled: {gameinfo_enabled}\033[0m")
    print(f"\033[32mImage Upload enabled: {image_upload_enabled}\033[0m")
    print(f"\033[32mCleanup enabled: {cleanup_enabled}\033[0m")
    print(f"\033[32mLoading filters: {filters_path}\033[0m")
    print(f"\033[32mLoading uploadlog: {upload_log}\n\033[0m")
    print(f"\033[31m################ Settings ################\033[0m")
    print()

    print(ascii_art_header("Login"))
    print("\033[0m\033[33mLogging in...\n\033[0m")
    # Login and get cookies
    try:
        cookies = login()  # Call the login function from login.utils.py
        if not cookies:
            log_to_file(log_file_path, "Login failed. Cannot proceed with the script.")
            print("\033[31mLogin failed. Cannot proceed with the script.\n\033[0m")
            return
        else:
            print("\033[92mLogin successful. Proceeding...\n\033[0m")
            # Continue with the rest of your script using the cookies
            # For example:
            # upload_data(cookies)
    except Exception as e:
        log_to_file(log_file_path, f"Error during login: {str(e)}")
        print(f"\033[91mError during login: {str(e)}\n\033[0m")
        return

    insert_upload(name=directory_name)

    # Create process-specific directory in TMP_DIR
    temp_dir = TMP_DIR

    # Initialize duplicate check variable
    duplicate_found = False

    # Check for duplicates
    try:
        # Read settings from config
        dupe_check_enabled = config.getboolean('Settings', 'DUPECHECK', fallback=False)
        dupe_dl_enabled = config.getboolean('Settings', 'DUPEDL', fallback=False)

        # Only run dupe check if both DUPECHECK and DUPEDL are enabled
        if dupe_check_enabled and dupe_dl_enabled:
            print(ascii_art_header("Dupe checking"))
            duplicate_found = check_and_download_dupe(directory_name, cookies)
            if duplicate_found:
                log("Duplicate found. Skipping further operations.", log_file_path)
                update_status(directory, 'dupe')
                update_upload_status(name=directory_name, new_status='dupe')
                log_upload_details(upload_details, upload_log_path, duplicate_found=True)
                cleanup_tmp_dir(TMP_DIR, cleanup_enabled)  # Clean up TMP_DIR
                return
        else:
            log("Dupe check or download is disabled in the config.", log_file_path)

    except Exception as e:
        log(f"Error checking for duplicates: {str(e)}", log_file_path)
        cleanup_tmp_dir(TMP_DIR, cleanup_enabled)  # Clean up TMP_DIR
        return

    update_upload_status(name=directory_name, new_status='uploading')
    print(ascii_art_header("Create Torrent"))
    # Create a torrent file and store it in the process-specific directory
    try:
        upload_details['etor_started'] = time.strftime('%a %b %d %H:%M:%S %Z %Y')
        
        # Capture both torrent_file and piece_size from create_torrent
        torrent_file, piece_size = create_torrent(directory, temp_dir)
        
        if torrent_file is None:
            raise Exception("Failed to create torrent file.")
        
        upload_details['torrent_file'] = torrent_file
        upload_details['piece_size'] = piece_size
        upload_details['etor_completed'] = time.strftime('%a %b %d %H:%M:%S %Z %Y')

    except Exception as e:
        log(f"Error creating torrent: {str(e)}", log_file_path)        
        return

    print(ascii_art_header("Category"))

    # Determine the category of the torrent
    category_name, category_id_str = determine_category(directory_name)
    category_id = int(category_id_str)  # Convert category_id to integer

    upload_details['category'] = f"{category_name} ({category_id})"

    update_upload_status(name=directory_name, new_status='uploading', size=f'{upload_details["size"]}', category=f'{category_name}')


    # Initialize replacements dictionary
    replacements = {}

    # Screenshots processing
    if screenshots_enabled:
        print(ascii_art_header("Screenshots"))
        if category_id in screenshot_categories:
            try:
                if rar2fs_screenshots_enabled and category_id in rar2fs_categories:
                    generate_screenshots(directory, category_id)
                else:
                    generate_screenshots(directory, category_id)
            except Exception as e:
                log(f"Error generating screenshots: {str(e)}", log_file_path)
                return
        else:
            log(f"Category ID {category_id} is not in the screenshot categories: {screenshot_categories}", log_file_path)
    else:
        log("Screenshots are disabled.", log_file_path)

    # Mediainfo processing
    mediainfo_content = ''
    if mediainfo_enabled:
        print(ascii_art_header("Mediainfo"))
        if category_id in mediainfo_categories:
            try:
                mediainfo_file_path = generate_mediainfo(directory, temp_dir)
                if mediainfo_file_path.exists():
                    with open(mediainfo_file_path, 'r') as file:
                        mediainfo_content = file.read()
                    # Insert mediainfo content into the template replacements
                    replacements['!mediainfo!'] = mediainfo_content
                else:
                    replacements['!mediainfo!'] = ''
            except Exception as e:
                log(f"Error generating mediainfo: {str(e)}", log_file_path)
                replacements['!mediainfo!'] = ''
        else:
            replacements['!mediainfo!'] = ''

    # IMDb processing
    imdb_id = ''
    imdb_link = ''
    if imdb_enabled:
        print(ascii_art_header("IMDB"))
        print(f"\033[33mFind IMDB data\n\033[0m")
        if category_id in imdb_movie_categories or category_id in imdb_tv_categories:
            # Attempt to extract IMDb link from .nfo file
            imdb_link = extract_imdb_link_from_nfo(directory)
            if imdb_link:
                print(f"\033[92mIMDb link found in NFO: {imdb_link}\n\033[0m")
                update_upload_status(name=directory_name, imdb_url=imdb_link)  # Update IMDb URL in DB
            else:
                if category_id in imdb_movie_categories:
                    print(f"\033[33mNo IMDb link found in NFO or no NFO file present. Attempting to extract movie details from title.\n\033[0m")
                    title, year = extract_movie_details(directory_name)
                    if title:
                        imdb_info = get_imdb_info(title, year)
                        if imdb_info:
                            imdb_link = f"https://www.imdb.com/title/{imdb_info['id']}/"
                            print(f"\033[92mIMDb link found: {imdb_link}\n\033[0m")
                            update_upload_status(name=directory_name, imdb_url=imdb_link)  # Update IMDb URL in DB
                        else:
                            print(f"\033[91mNo IMDb info found.\033[0m")
                    else:
                        print(f"\033[91mCould not extract movie details from directory name.\033[0m")
                elif category_id in imdb_tv_categories:
                    print(f"\033[33mNo IMDb link found in NFO or no NFO file present. Attempting to extract TV show details from title.\n\033[0m")
                    title, season, episode = extract_tv_show_details(directory_name)
                    if title:
                        imdb_info = get_imdb_tv_info(title, season, episode)
                        if imdb_info:
                            imdb_link = f"https://www.imdb.com/title/{imdb_info['id']}/"
                            print(f"\033[92mIMDb link found: {imdb_link}\n\033[0m")
                            update_upload_status(name=directory_name, imdb_url=imdb_link)  # Update IMDb URL in DB
                        else:
                            print(f"\033[91mNo IMDb info found.\033[0m")
                    else:
                        print(f"\033[91mCould not extract TV show details from directory name.\033[0m")
        else:
            print(f"\033[33mCategory ID {category_id} is not in the IMDb categories: {imdb_movie_categories} or {imdb_tv_categories}\033[0m")            

    imdb_id = re.search(r'tt\d+', imdb_link).group() if imdb_link else ''


    # Game information processing
    if gameinfo_enabled and category_id in game_categories:
        print(ascii_art_header("Gameinfo"))
        print("\033[33mFetching game information...\n\033[0m")
        try:
            # Use the correct function for extracting the game name from the release name or directory
            game_name = extract_game_name(directory_name)  # Ensure this function exists and works

            if game_name:
                print(f"\033[33mExtracted Game Name: {game_name}\033[0m")

                # Fetch game information from IGDB
                game_info = fetch_game_info(game_name, directory_name)

                if game_info:
                    # Extract relevant game info
                    game_summary = game_info['summary']
                    game_genres = ', '.join(game_info['genres'])
                    game_release_date = game_info['release_date']


                    # Prepare the game info content for the template with BBCode formatting
                    gameinfo_content = (
                        f"[b]Game:[/b] [color=purple]{game_info['game_name']}[/color]\n"
                        f"[b]Summary:[/b] [i]{game_summary}[/i]\n"
                        f"[b]Genres:[/b] [color=green]{game_genres}[/color]\n"
                        f"[b]Release Date:[/b] [color=cyan]{game_release_date}[/color]\n"
                    )

                    # Log and display fetched game info
                    print(f"\033[32mFetched Game Info:\n{gameinfo_content}\033[0m")

                    # Insert gameinfo content into replacements
                    replacements['!gameinfo!'] = gameinfo_content
                    print("\033[32mGame information successfully fetched and added to template!\033[0m")
                else:
                    # Handle case when no game info is found
                    replacements['!gameinfo!'] = ''
                    print(f"\033[31mNo game information found for {game_name}.\n\033[0m")
            else:
                print("\033[31mGame name could not be extracted from the NFO or directory.\n\033[0m")
                replacements['!gameinfo!'] = ''

        except Exception as e:
            # Handle exceptions and log errors
            replacements['!gameinfo!'] = ''
            log(f"Error fetching game information: {str(e)}", log_file_path)
            print(f"\033[31mError fetching game information: {str(e)}\033[0m")
    else:
        # If gameinfo is disabled or category is not in game categories
        replacements['!gameinfo!'] = ''

    # Image upload processing
    print(ascii_art_header("UploadImages"))
    if image_upload_enabled:
        print(f"\033[33mUploading images...\n\033[0m")
        try:
            # Collect all image URLs from the source directory
            source_image_urls = upload_images(directory)
            
            if source_image_urls:
                image_urls_str = '\n'.join(source_image_urls)
                update_upload_status(name=directory_name, image_url=image_urls_str)
                replacements['!imageupload!'] = '\n'.join(source_image_urls)
                print(f"\033[32mImage upload successful!\n\033[0m")  # Print success message
            else:
                replacements['!imageupload!'] = ''
                print(f"\033[31mNo images found in the source directory.\n\033[0m")  # Print no images found message

            # Upload the screenshots and get URLs
            if screenshots_enabled:
                print(f"\033[33mUploading screenshots...\n\033[0m")
                screenshots_dir = TMP_DIR / 'screens'
                if screenshots_dir.exists():
                    screenshot_urls = upload_images(screenshots_dir, is_screenshots=True)
                    
                    if screenshot_urls:
                        screenshot_urls_str = '\n'.join(screenshot_urls)
                        update_upload_status(name=directory_name, screenshot_url=screenshot_urls_str)
                        replacements['!screenshots!'] = '\n'.join(screenshot_urls)
                        print(f"\033[32mScreenshot upload successful!\033[0m")  # Print success message
                    else:
                        replacements['!screenshots!'] = ''
                        print(f"\033[31mNo screenshots found.\n\033[0m")  # Print no screenshots found message
                else:
                    replacements['!screenshots!'] = ''
                    print(f"\033[31mScreenshots directory not found or it is empty.\n\033[0m")

            # Upload the game images if game info is available and game images exist
            game_image_dir = TMP_DIR / 'images'
            if game_image_dir.exists() and any(game_image_dir.iterdir()):
                print(f"\033[33mUploading game images...\n\033[0m")

                # Sort files based on the number prefix (1-cover, 2-screenshot, etc.)
                sorted_images = sorted(game_image_dir.iterdir(), key=lambda x: int(x.name.split('-')[0]))

                # Ensure the first image is cover image if it exists
                cover_image = [img for img in sorted_images if '1-cover' in img.name]
                remaining_images = [img for img in sorted_images if '1-cover' not in img.name]

                # Combine the cover and remaining images, ensuring the cover is first
                sorted_images = cover_image + remaining_images

                # Pass the directory (sorted) to the upload_images function
                game_image_urls = upload_images(game_image_dir, is_screenshots=False)

                if game_image_urls:
                    game_image_urls_str = '\n'.join(game_image_urls)
                    update_upload_status(name=directory_name, image_url=game_image_urls_str)
                    replacements['!gameimage!'] = '\n'.join(game_image_urls)
                    print(f"\033[32mGame image upload successful!\n\033[0m")
                else:
                    replacements['!gameimage!'] = ''
                    print(f"\033[31mNo game images found.\n\033[0m")
            else:
                replacements['!gameimage!'] = ''
                print(f"\033[31mNo game images directory found.\n\033[0m")

        except Exception as e:
            log(f"Error uploading images: {str(e)}", log_file_path)
            print(f"\033[31mError uploading images: {str(e)}\033[0m")  # Print error message

    # Process .nfo file
    print(ascii_art_header("NFO"))
    print(f"\033[33m\nFinding NFO data...\n\033[0m")
    try:        
        process_nfo(directory, replacements, log_file_path)
    except Exception as e:
        log(f"Error processing .nfo file: {str(e)}", log_file_path)

    print(f"\033[32mAdd directory name to template\n\033[0m")
    replacements['!releasename!'] = directory_name

   # Prepare and save the final template with all content
    try:
        output_template_path = os.path.join(TMP_DIR, 'output_template.txt')
        prepare_template(TEMPLATE_PATH, output_template_path, replacements)

        # Read the template content after replacements
        with open(output_template_path, 'r', encoding='utf-8') as file:
            template_content = file.read()

        # Remove empty lines
        template_content = "\n".join([line for line in template_content.splitlines() if line.strip()])

        # Remove empty BBCode tags (e.g., [tag][/tag], [tag][tag2][/tag2][/tag])
        template_content = re.sub(r'\[([a-zA-Z0-9]+)\]\s*\[\/\1\]', '', template_content)

        # Save the cleaned content back to the file
        with open(output_template_path, 'w', encoding='utf-8') as file:
            file.write(template_content)

        # Correctly use the path to the file, not the content itself
        template_content = output_template_path  # This ensures the path is used later

    except FileNotFoundError as e:
        log(f"File not found: {str(e)}", log_file_path)
    except Exception as e:
        log(f"Error preparing template: {str(e)}", log_file_path)

    #time.sleep(3)

    # Upload the torrent
    print(ascii_art_header("Uploading"))

    # Print and log variables before upload
    print("\033[33mUploading torrent...\n\033[0m")
    #print(f"Torrent file: {torrent_file}")
    #print(f"Template content: {template_content}")
    #print(f"Cookies: {cookies}")
    #print(f"Category ID: {category_id}")
    #print(f"IMDB ID: {imdb_id}")
    #print(f"Mediainfo content length: {len(mediainfo_content) if mediainfo_content else '0'}")

    # Log variables
    log(f"Torrent file: {torrent_file}", log_file_path)
    log(f"Template content: {template_content}", log_file_path)
    log(f"Cookies: {cookies}", log_file_path)
    log(f"Category ID: {category_id}", log_file_path)
    log(f"IMDB ID: {imdb_id}", log_file_path)
    log(f"Mediainfo content length: {len(mediainfo_content) if mediainfo_content else '0'}", log_file_path)
    # Initialize upload details dictionary

    try:
        upload_torrent(torrent_file, template_content, cookies, category_id, imdb_id, mediainfo_content)
        log_upload_details(upload_details, upload_log_path, duplicate_found=False)
        update_status(directory, 'uploaded')
        update_upload_status(name=directory_name, new_status='uploaded')
        print(f"Torrent uploaded successfully. Details logged at: {upload_log_path}")
    except Exception as e:
        log(f"Error uploading torrent: {str(e)}", log_file_path)
        # Optionally, you can log details even when an exception occurs, if relevant
        #log_upload_details(upload_details, upload_log_path, duplicate_found=False)
        print(f"Failed to upload torrent. Error: {str(e)}")

    # Cleanup TMP_DIR
    cleanup_tmp_dir(TMP_DIR, cleanup_enabled)

if __name__ == "__main__":
    main()

