import re
import subprocess
from pathlib import Path


def generate_mediainfo(directory, tmp_dir):
    """Generate media info for movie files in the given directory using the mediainfo executable, and save to a file in tmp_dir."""
    movie_extensions = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.flv', '*.wmv', '*.mpg', '*.mpeg', '*.webm', '*.m4v']
    
    mediainfo_output = ""
    print(f"\033[33mCreating mediainfo for directory: {directory}\n\033[0m") 

    # Collect all movie files matching the extensions recursively
    media_files = []
    for ext in movie_extensions:
        found_files = list(Path(directory).rglob(ext))
        print(f"Found {len(found_files)} files with extension {ext}: {found_files}")
        media_files.extend(found_files)
    
    if not media_files:
        print("\033[91mNo media files found.\033[0m")  # Red text for no files found
    
    for media_file in media_files:
        try:
            print(f"Processing file: {media_file}\n")
            # Run mediainfo command and capture output
            result = subprocess.run(
                ['mediainfo', str(media_file)],
                text=True,
                capture_output=True,
                check=True
            )
            """ Stored for quick undo. For now, just use one file's media info.
            file_info = result.stdout
            # Remove lines containing "Complete name:" with any amount of space or tab before the colon
            file_info = "\n".join(line for line in file_info.splitlines()
                                  if not re.match(r'\s*Complete name\s*:', line))
            mediainfo_output += file_info + "\n\n"
            """
            mediainfo_output = result.stdout
            # Remove lines containing "Complete name:" with any amount of space or tab before the colon
            mediainfo_output = "\n".join(line for line in mediainfo_output.splitlines()
                                  if not re.match(r'\s*Complete name\s*:', line))
            break
        except subprocess.CalledProcessError as e:
            # Handle errors in running mediainfo
            print(f"\033[91mError getting media info for {media_file}: {e}\033[0m")  # Red text for errors
            # Reset mediainfo_output for next run
            mediainfo_output = None

    # Save mediainfo output to a file in the tmp_dir
    mediainfo_file_path = None
    if mediainfo_output:
        mediainfo_output = f"[mediainfo]\n{mediainfo_output.strip()}\n[/mediainfo]"
        mediainfo_file_path = Path(tmp_dir) / 'mediainfo_output.txt'
        with open(mediainfo_file_path, 'w') as file:
            file.write(mediainfo_output)
        
        print(f"\033[92mMediaInfo created and saved to: {mediainfo_file_path}\n\033[0m")  # Green text for success
    
    return mediainfo_file_path
