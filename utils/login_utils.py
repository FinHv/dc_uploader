import requests
import os
import pickle
import warnings
from pathlib import Path
from utils.config_loader import ConfigLoader
from utils.logging_utils import log_to_file

# Suppress InsecureRequestWarning (not recommended for production)
warnings.simplefilter('ignore', requests.packages.urllib3.exceptions.InsecureRequestWarning)

# Load the configuration
config = ConfigLoader().get_config()

# Create a unique process directory
process_id = os.getpid()
TMP_DIR = Path(config.get('Paths', 'TMP_DIR')) / str(process_id)
COOKIE_PATH = Path(config.get('Paths', 'COOKIE_PATH'))

# Ensure the TMP_DIR exists
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Captcha Passkey and other credentials from config
CAPTCHA_PASSKEY = config.get('Website', 'CAPTCHA_PASSKEY')
SITEURL = config.get('Website', 'SITEURL')
USERNAME = config.get('Website', 'USERNAME')
PASSWORD = config.get('Website', 'PASSWORD')
LOGINTXT = config.get('Website', 'LOGINTXT')  # Text to confirm successful login

# Login URL
LOGINURL = f"{SITEURL}/api/v1/auth?password={PASSWORD}&username={USERNAME}&captcha={CAPTCHA_PASSKEY}"

def save_cookies(cookies, path):
    """Save cookies to a file."""
    with open(path, 'wb') as f:
        pickle.dump(cookies, f)

def load_cookies(path):
    """Load cookies from a file."""
    if path.exists():
        with open(path, 'rb') as f:
            return pickle.load(f)
    return None

def login():
    """Perform login to the website and return cookies for subsequent requests."""
    session = requests.Session()  # Use a session to persist cookies and headers
    user_agent = 'Mozilla/5.0'
    
    # Try to load existing cookies
    existing_cookies = load_cookies(COOKIE_PATH)
    if existing_cookies:
        print("\033[0m\033[32mUsing existing cookies...\n\033[0m")
        session.cookies.update(existing_cookies)
        return session.cookies
    
    try:
        # Perform the login request
        response = session.get(LOGINURL, headers={'User-Agent': user_agent}, verify=False)
        
        # Save cookies to a file
        save_cookies(session.cookies, COOKIE_PATH)
        
        # Log the request and response details
        log_to_file(TMP_DIR / 'login_request.log', f"Login URL: {LOGINURL}\nHeaders: {{'User-Agent': user_agent}}")
        log_to_file(TMP_DIR / 'login_response.log', f"Response Status: {response.status_code}\nResponse Text: {response.text}")
        
        # Check if login was successful
        if response.status_code == 200 and LOGINTXT in response.text:
            print(f"\033[92mLogin successful.\n\033[0m")
            return session.cookies
        else:
            print(f"\033[91mLogin failed. Status code: {response.status_code}\033[0m")
            return None
    except requests.RequestException as e:
        # Log any request exceptions
        log_to_file(TMP_DIR / 'login_error.log', f"Login request failed: {str(e)}")
        print(f"\033[91mLogin request failed: {str(e)}\033[0m")
        return None
