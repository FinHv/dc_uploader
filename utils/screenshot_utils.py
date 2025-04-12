import os
import re
import subprocess
from pathlib import Path

from utils.config_loader import ConfigLoader

# Load configuration settings
config = ConfigLoader().get_config()

def generate_screenshots(directory, category_id):
    """Generate screenshots for movie files in the given directory using the MTN tool."""
    mtn_width = config.get('MediaTools', 'MTNWIDTH')
    mtn_postby = config.get('MediaTools', 'MTNPOSTBY')
    mtn_setting = config.get('MediaTools', 'MTNSETTING')
    mtn_fontfile = config.get('MediaTools', 'MTNFONTFILE')
    tmp_dir = Path(config.get('Paths', 'TMP_DIR'))

    # Define paths for temporary files
    tmp_dir = tmp_dir / str(os.getpid())
    screenshots_dir = tmp_dir / 'screens'
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    mounts_dir = tmp_dir / 'mounts'
    mounts_dir.mkdir(parents=True, exist_ok=True)

    # Prepare the command options
    command_opts = f"{mtn_width} {mtn_postby} {mtn_setting} -f {mtn_fontfile} -h 150 -q"

    # Check if screenshots are enabled and category is in the configured list
    screenshots_enabled = config.getboolean('Settings', 'SCREENSHOTS')
    rar2fs_screenshots_enabled = config.getboolean('Settings', 'RAR2FS_SCREENSHOTS')
    screenshot_categories = set(map(int, config.get('Settings', 'SCREENSHOT_CATEGORIES').split(',')))
    rar2fs_categories = set(map(int, config.get('Settings', 'RAR2FS_CATEGORIES').split(',')))

    if not screenshots_enabled or category_id not in screenshot_categories:
        print("Screenshots are disabled or category ID is not in the screenshot categories.")
        return

    # Check if RAR2FS should be used
    if rar2fs_screenshots_enabled and category_id in rar2fs_categories:
        print(f"\033[33mRAR2FS Enabled, mounting RAR files\n\033[0m")
        rar_files = list(Path(directory).rglob('*.rar'))
        if rar_files:
            for rar_file in rar_files:
                mount_point = mounts_dir / str(os.getpid())
                mount_point.mkdir(parents=True, exist_ok=True)
                try:
                    # Mount RAR file using rar2fs
                    subprocess.run(['rar2fs', '-o', 'allow_other', '--seek-length=1', str(rar_file), str(mount_point)], check=True)
                    # Process movie files
                    process_movie_files(mount_point, command_opts, screenshots_dir)
                finally:
                    # Clean up mount point
                    subprocess.run(['fusermount', '-u', str(mount_point)], check=True)
                    mount_point.rmdir()
        else:
            # Process movie files directly if no RAR files found
            process_movie_files(directory, command_opts, screenshots_dir)
    else:
        # Process movie files directly if RAR2FS is not enabled
        process_movie_files(directory, command_opts, screenshots_dir)
    

def process_movie_files(directory, command_opts, screenshots_dir, is_rar2fs=False):
    """Process movie files to generate screenshots using MTN."""
    valid_movie_extension = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.flv', '*.wmv', '*.mpg', '*.m2ts', '*.vob']
    media_files = []
    root_files = []
    screenshots_generated = False
    
    print(f"\033[33mCreating screenshots\n\033[0m")
    
    # Collect movie files in the root of the directory
    for ext in valid_movie_extension:
        root_files.extend(Path(directory).glob(ext))
    
    # Determine if there are any movie files in the root directory
    has_root_movie = len(root_files) > 0

    # Collect all movie files recursively
    for ext in valid_movie_extension:
        media_files.extend(Path(directory).rglob(ext))
    
    if not media_files:
        print("\033[91mNo media files found.\033[0m")  # Red text for no files found
        return

    # Log the number of media files found
    print(f"Found {len(media_files)} media files.")

    for media_file in media_files:
        # Determine if we should skip this file based on the sample folder logic
        skip_file = False
        if has_root_movie and not is_rar2fs:
            if re.search(r'[Ss][Aa][Mm][Pp][Ll][Ee]', str(media_file)):
                skip_file = True
        if skip_file:
            print(f"\033[33mSkipping sample file: {media_file}\033[0m")
            continue

        print(f"Processing file: {media_file}")
        try:
            # Run MTN to generate screenshots
            screenshots_generated = mtn_exec(command_opts, media_file, [config.get('MediaTools', 'MTNBIN')], screenshots_dir)
            if not screenshots_generated:
                print(f"Trying again with fallback mtn binary")
                screenshots_generated = mtn_exec(command_opts, media_file, 'bin/mtn/mtn-fallback', screenshots_dir)
                if not screenshots_generated:
                    # Still can't generate screenshots
                    print(f"No screenshots generated for {media_file} with fallback mtn binary. Possibly broken media file")
                else:
                    # We successfully got screenshots, break out of the loop
                    break
            else:
                # We successfully got screenshots, break out of the loop
                break
        except subprocess.CalledProcessError as e:
            print(f"\033[91mError creating screenshots for {media_file}: {e}\033[0m")  # Red text for errors
        except Exception as e:
            print(f"\033[91mUnexpected error for {media_file}: {e}\033[0m")  # Red text for unexpected errors

    # If no screenshots were generated, and it's not a RAR2FS mount, check sample directories
    if not screenshots_generated and not is_rar2fs:
        print(f"\033[33mNo screenshots generated from mounted files. Checking sample directories...\033[0m")
        # Process movie files in sample directories if no screenshots were generated
        sample_dirs = [d for d in Path(directory).rglob('*[Ss][Aa][Mm][Pp][Ll][Ee]*') if d.is_dir()]
        if sample_dirs:
            print(f"Found sample directories: {sample_dirs}")
        for sample_dir in sample_dirs:
            process_movie_files(sample_dir, command_opts, screenshots_dir, is_rar2fs=False)


def mtn_exec(command_opts, media_file, mtn_path, screenshots_dir):
    command = mtn_path + command_opts.split() + [str(media_file), '-o', '.jpg', '-O', str(screenshots_dir)]
    print(f"Running command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    # Debug
    # print(f"Command output: {result.stdout}")
    # print(f"Command error: {result.stderr}")
    if result != 0:
        print(f"Failed to generate screenshots for {media_file}.")
        return False

    # Check if any screenshot files are created
    screenshot_files = list(screenshots_dir.glob(f"{media_file.stem}*.jpg"))
    if screenshot_files:
        print(f"Successfully generated screenshots")
        print(f"Generated screenshots: {screenshot_files}")
        return True
    else:
        print(f"No screenshots generated for {media_file}.")
        return False
