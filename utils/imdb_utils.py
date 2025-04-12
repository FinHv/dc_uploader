import json
import os
import re
from pathlib import Path

import requests

from utils.bcolors import bcolors
from utils.config_loader import ConfigLoader

# Load configuration
config = ConfigLoader().get_config()


def extract_tv_show_details(directory_name):
    """Extract the TV show title, season, and episode from the directory name."""
    # Example pattern: 13.Reasons.Why.S03E10.MULTI.HDR.2160p.WEB.H265-HiggsBoson
    match = re.match(r'(.+?)\.[sS](\d{2})[eE](\d{2})', directory_name)
    
    if match:
        title, season, episode = match.groups()
        title = title.replace('.', ' ').strip()  # Replace dots with spaces
        #print(f"Extracted TV show title: {title}, season: {season}, episode: {episode}")
        return title, season, episode
    
    print(f"Failed to extract TV show details from directory name.")
    return None, None, None


def get_imdb_tv_info(title, season=None, episode=None):
    """Fetch IMDb info based on the TV show title, season, and episode from TMDb."""
    print(f"{bcolors.YELLOW}Trying to extract IMDb info from TV show title: {title}\n{bcolors.ENDC}")
    
    # Load API key from configuration
    api_key = config.get('TMDB', 'APIKEY')
    
    # Prepare the query for TV show search
    query = title
    imdb_api_url = f"https://api.themoviedb.org/3/search/tv?api_key={api_key}&query={query}"
    
    print(f"Searching IMDbId info from TMDb with URL: {imdb_api_url}")

    try:
        response = requests.get(imdb_api_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()

        # Log the received data
        print(f"Received data: {json.dumps(data, indent=2)}")

        # Check if there are any results
        if 'results' in data and data['results']:
            print(f"{bcolors.OKGREEN}TMDb info fetched successfully.\n{bcolors.ENDC}")
            
            # Iterate over results
            for result in data['results']:
                tv_show_id = result['id']
                tv_show_title = result['name']
                release_year = result.get('first_air_date', '').split('-')[0]  # Extract only the year part

                print(f"Processing result: {tv_show_title} ({release_year})")

                # Fetch IMDb ID for the show
                imdb_id = fetch_imdb_id(tv_show_id, api_key, is_tv=True)
                
                if imdb_id:
                    print(f"{bcolors.OKGREEN}IMDb ID: {imdb_id} found for the TV show.\n{bcolors.ENDC}")
                    return {"id": imdb_id, "title": tv_show_title, "year": release_year}
                
            print(f"{bcolors.FAIL}No matching IMDb results found for the TV show.\n{bcolors.ENDC}")
        else:
            print(f"{bcolors.FAIL}No IMDb results found for the TV show.\n{bcolors.ENDC}")
        
    except requests.exceptions.RequestException as e:
        print(f"{bcolors.FAIL}Error fetching IMDb info: {str(e)}\n{bcolors.ENDC}")
    
    return None




def get_imdb_info(title, year=None):
    """Fetch IMDb info based on the title and optional year from TMDb."""
    #print(f"{bcolors.YELLOW}Trying to extract IMDb info from title: {title}\n{bcolors.ENDC}")
    
    # Load API key from configuration
    config = ConfigLoader().get_config()
    api_key = config.get('TMDB', 'APIKEY')
    
    # Prepare the query without including the year
    query = title
    imdb_api_url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query}"
    
    #print(f"Searching IMDbId info from TMDb with URL: {imdb_api_url}")

    try:
        response = requests.get(imdb_api_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()

        # Log the received data
        #print(f"Received data: {json.dumps(data, indent=2)}")

        # Check if there are any results
        if 'results' in data and data['results']:
            print(f"{bcolors.OKGREEN}TMDb info fetched successfully.\n{bcolors.ENDC}")
            
            # Iterate over results and compare the year
            for result in data['results']:
                release_year = result.get('release_date', '').split('-')[0]  # Extract only the year part

                # Log each result being processed
                #print(f"Processing result: {result['title']} ({release_year})")
                
                if year:
                    #print(f"Checking if result year {release_year} matches provided year {year}")
                    if release_year == str(year):
                        # If the years match, fetch the IMDb ID
                        movie_id = result['id']
                        #print(f"Found matching movie ID: {movie_id}, fetching IMDb ID...")
                        
                        imdb_id = fetch_imdb_id(movie_id, api_key)
                        
                        if imdb_id:
                            print(f"{bcolors.OKGREEN}IMDb ID: {imdb_id} found for the movie.\n{bcolors.ENDC}")
                            return {"id": imdb_id, "title": result['title'], "year": release_year}
                        else:
                            print(f"{bcolors.FAIL}Failed to fetch IMDb ID for movie ID: {movie_id}\n{bcolors.ENDC}")
                    else:
                        print(f"Skipping result due to year mismatch: {release_year} != {year}")
                else:
                    # If no year is provided, just return the first result
                    movie_id = result['id']
                    imdb_id = fetch_imdb_id(movie_id, api_key)
                    if imdb_id:
                        print(f"{bcolors.OKGREEN}IMDb ID: {imdb_id} found for the movie.\n{bcolors.ENDC}")
                        return {"id": imdb_id, "title": result['title'], "year": release_year}

            print(f"{bcolors.FAIL}No matching IMDb results found for the title with the given year.\n{bcolors.ENDC}")
        else:
            print(f"{bcolors.FAIL}No IMDb results found for the title.\n{bcolors.ENDC}")
        
    except requests.exceptions.RequestException as e:
        print(f"{bcolors.FAIL}Error fetching IMDb info: {str(e)}\n{bcolors.ENDC}")
    
    return None

def fetch_imdb_id(media_id, api_key, is_tv=False):
    """Fetch the IMDb ID for a given movie or TV show ID from TMDb."""
    media_type = 'tv' if is_tv else 'movie'
    imdb_id_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}/external_ids?api_key={api_key}"
    
    print(f"Fetching IMDb ID with URL: {imdb_id_url}")

    try:
        response = requests.get(imdb_id_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        
        print(f"Received data for IMDb ID: {json.dumps(data, indent=2)}")

        if 'imdb_id' in data and data['imdb_id']:
            return data['imdb_id']
        else:
            print(f"{bcolors.FAIL}No IMDb ID found for {media_type} ID: {media_id}\n{bcolors.ENDC}")
            return None
    
    except requests.exceptions.RequestException as e:
        print(f"{bcolors.FAIL}Error fetching IMDb ID: {str(e)}\n{bcolors.ENDC}")
        return None


def extract_imdb_link_from_nfo(directory):
    """Extract IMDb link from a .nfo file in the directory."""
    nfo_files = list(Path(directory).glob('*.nfo'))

    for nfo_file in nfo_files:
        nfo = os.path.basename(nfo_file)
        print(f"{bcolors.YELLOW}Trying to extract IMDb data from: {nfo}\n{bcolors.ENDC}")
        
        with open(nfo_file, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            # Match various IMDb link formats, including HTTPS and non-www URLs
            match = re.search(r'https?://(?:www\.)?imdb\.com/title/tt\d+', content)
            if match:
                #print(f"{bcolors.OKGREEN}IMDb link found: {match.group(0)}\n{bcolors.ENDC}")
                return match.group(0)
    
    print(f"{bcolors.FAIL}No IMDb link found in NFO files.\n{bcolors.ENDC}")
    return None

def extract_movie_details(directory_name):
    """Extract the movie title and year from the directory name."""
    #print(f"Extracting movie details from directory name: {directory_name}")
    
    # Attempt to match patterns like "Title (Year)" or "Title.Year"
    match = re.match(r'(.+?)[\s.]*\((\d{4})\)', directory_name)
    if not match:
        match = re.match(r'(.+?)[\s.]*(\d{4})', directory_name)
    
    if match:
        title, year = match.groups()
        title = title.replace('.', ' ').strip()  # Replace dots with spaces
        #print(f"Extracted title: {title}, year: {year}")
        return title, year.strip()
    
    print(f"Failed to extract title and year from directory name.")
    return None, None
