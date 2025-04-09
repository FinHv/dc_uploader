#!/bin/bash

print_help() {
    echo "Script usage: $(basename "$0") [OPTION]"
    echo "Optional arguments:"
    echo "-y: Answer yes to all warnings"
    echo
    echo "-d, --domain: Fully qualified domain name (e.g. hostname.domain.tld) you wish to use for the web app."\
    "If provided, uses certbot to request certificates from Let's Encrypt. Default if not provided: self-signed"
    echo
    echo "-v, --venv: Path where virtual environment is install to. Default if not provided: /opt/dcc-uploader"
    echo
    echo "-c, --cloudflare: Use cloudflare DNS challenge if you want to use Cloudflare DNS challenge instead of HTTP"\
    "challenge. Will automatically install certbot cloudflare plugins."
    echo
    echo "-t, --cloudflare-token: Cloudflare API token to use for Cloudflare DNS challenge. If a token is provided,"\
    "-c/--cloudflare is automatically assumed and user does not need to provide that argument. Token will be stored in"\
    "/root/.secrets/cloudflare.ini post-install. Attempts to re-use token found in cloudflare.ini if -c/--cloudflare"\
    "is set but no token is provided."
    echo "NOTE: providing a Cloudflare API token when one already exists in /root/.secrets/cloudflare.ini will result"\
    "in the existing one being used, and the provided one ignored. If you wish to update the token in cloudflare.ini,"\
    "you must do so manually."
    echo
    echo "-h, --help: Show this help page"
}

set -e

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

certbot_cf() {
    if [ -f "/root/.secrets/cloudflare.ini" ] \
    && cat /root/.secrets/cloudflare.ini | grep -qP '^dns_cloudflare_api_token ?= ?\S{40}'; then
        echo "Cloudflare credentials with valid length token already exists, reusing existing credentials."
    else
        # No valid pre-existing cloudflare.ini found
        if ! $ARGS_USED; then
            read -rp "Cloudflare API token : " CF_TOKEN
            if [ -z "$CF_TOKEN" ]; then
                echo "No Cloudflare token supplied, cannot continue" >&2
                exit 1
            fi
        else
            # Check to see if user provided a token when using arg mode.
            # There wasn't a valid one to reuse, so it needs to be provided
            if [ -z "$CF_TOKEN" ]; then
                echo "No Cloudflare token supplied and no valid tokens were found in cloudflare.ini, aborting" >&2
                exit 1
            fi
        fi
        mkdir /root/.secrets/
        touch /root/.secrets/cloudflare.ini
        echo "dns_cloudflare_api_token = $CF_TOKEN" | tee /root/.secrets/cloudflare.ini
        chmod 0700 /root/.secrets/
        chmod 0600 /root/.secrets/cloudflare.ini
        echo "Cloudflare credentials created"
    fi
    echo "Installing certbot cloudflare plugin..."
    /opt/certbot/bin/pip install certbot-dns-cloudflare
    echo "Calling certbot for credentials using DNS challenge..."
    certbot certonly --agree-tos --register-unsafely-without-email --key-type ecdsa --elliptic-curve secp384r1 \
    --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/cloudflare.ini -d "$SERVER_NAME"
}

add_auto_renewal(){
    # Adds renewal to cron
    if ! cat /etc/crontab | grep -q "certbot renew -q"; then
        # At 12AM and 12PM every day. Will only renew certificates if eligible for automatic renewal
        echo "0 0,12 * * * root /opt/certbot/bin/python -c"\
        "'import random; import time; time.sleep(random.random() * 3600)' && sudo certbot renew -q" | \
        tee -a /etc/crontab > /dev/null
    fi
    if ! cat /etc/crontab | grep -q "/opt/certbot/bin/pip install --upgrade certbot"; then
        # At 8am on the first day of the month
      echo "0 8 1 * * root /opt/certbot/bin/pip install --upgrade certbot" | tee -a /etc/crontab > /dev/null
    fi
}

handle_reply() {
    # Store in local variables
    RPLY=$1
    NO_MSG=$2
    # If the no response should be piped to stderr
    TO_ERROR=${3:-false}

    if [[ "$RPLY" =~ ^[Yy]$ ]]; then
        # Continue install, but echo once to make lines cleaner
        echo
        return 0
    elif [[ "$RPLY" =~ ^[Nn]$ ]]; then
        echo
        if $TO_ERROR; then
            echo "$NO_MSG" >&2
        else
            echo "$NO_MSG"
        fi
        return 1
    elif [ -z "$RPLY" ]; then
        if $TO_ERROR; then
            echo "$NO_MSG" >&2
        else
            echo "$NO_MSG"
        fi
        return 1
    else
        echo
        echo "Invalid input. Only y/n are accepted (case insensitive)" >&2
        exit 1
    fi
}

# Set default values if not provided
YES=false
ARGS_USED=false
USE_DOMAIN=false
VENV_PATH=/opt/dcc-uploader
USE_CLOUDFLARE=false

if [ $# -ne 0 ]; then
    # Only bother parsing args if an arg beside path is specified
    if ! OPTS=$(getopt -o 'hyd:v:t:,c'\-l 'help,domain:,venv:,cloudflare-token:,--cloudflare' -n "$(basename "$0")" -- "$@"); then
        echo "Failed to parse options" >&2
        print_help
        exit 1
    fi
    # Reset the positional parameters to the parsed options
    eval set -- "$OPTS"
    # Process arguments
    while true; do
        case "$1" in
            -y )
                YES=true
                shift
                ;;
            -d | --domain)
                SERVER_NAME="$2"
                ARGS_USED=true
                USE_DOMAIN=true
                shift 2
                ;;
            -v | --venv)
                VENV_PATH="$2"
                ARGS_USED=true
                shift 2
                ;;
            -t | --cloudflare-token)
                CF_TOKEN="$2"
                USE_CLOUDFLARE=true
                ARGS_USED=true
                shift 2
                ;;
            -c | --cloudflare)
                USE_CLOUDFLARE=true
                ARGS_USED=true
                shift
                ;;
            -h | --help)
                print_help
                exit 0
                ;;
            --)
                shift
                break
                ;;
            *)
                echo "Unrecognized argument" >&2
                print_help
                exit 1
                ;;
        esac
    done
fi



if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or with sudo" >&2
    exit 1
fi

. /etc/os-release

if [ "$ID" != "ubuntu" ]; then
    echo "This program was only built for ubuntu, aborting install" >&2
    exit 1
fi

# Move to install.sh root directory
SCRIPT_PATH=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )

cd "$SCRIPT_PATH"


if ! $ARGS_USED; then
    # Ask user if they want to use a domain or a self-signed certificate
    read -rp "Enter the path for the python virtual environment [default: /opt/dcc-uploader] : "
    VENV_PATH=${REPLY:-/opt/dcc-uploader}
fi

if ! ARGS_USED; then
    # Initiate server name to hostname in case user selects N. Needed for handle_reply.
    SERVER_NAME=$(hostname -f)

    read -rp -n 1 "Do you want to use a domain with Let's Encrypt? Defaults to self signed [y/n, default: n]: "

    if handle_reply "$REPLY" "Using self-signed certificate for server name: $SERVER_NAME" false; then
        # User chooses to use a domain
        echo "Info: If a Let's Encrypt certificate for the requested domain already exists, it will be imported"\
        "instead of creating a new certificate"
        read -rp "Enter the fully qualified domain name for the server for Let's Encrypt : " SERVER_NAME
        USE_DOMAIN=true
    else
        # User chooses to use a self-signed certificate
        USE_DOMAIN=false
    fi
else
    # Args provided, check if domain is set.
    if [ -z "SERVER_NAME" ]; then
        # No domain name was provided in the args. Assume self-signed
        USE_DOMAIN=false
    else
        # Some domain name was provided (validation done next). Assume SSL
        USE_DOMAIN=true
fi

# Domain name validation if SSL is being used
if $USE_DOMAIN; then
    if [ -z "$SERVER_NAME" ]; then
        echo "No domain name provided." >&2
        exit 1
    elif ! echo "$SERVER_NAME" | grep -qP '(?=^.{4,253}$)(^((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63}$)'; then
        echo "Invalid domain name provided." >&2
        exit 1
    fi
fi

# Clean up the venv path
VENV_PATH=$(realpath -s "$VENV_PATH")

# Add the PPA repository if not already added
if ! [ -f /etc/apt/sources.list.d/wahibre-ubuntu-mtn-noble.sources ]; then
    echo "Movie thumbnailer repo not detected in apt source, adding"
    add-apt-repository -y ppa:wahibre/mtn
fi

# Update to ensure newest versions are installed (assuming not already installed)
apt-get update

# Required packages
echo "Installing required tools and their dependencies..."
apt-get install build-essential mtn mediainfo libfuse-dev screen software-properties-common autoconf -y

# Install rar2fs
if [[ ! -f /usr/local/bin/rar2fs ]]; then
    echo "Installing rar2fs..."
    UNRAR_VER="7.1.6"
    RAR2FS_VER="1.29.7"
    WORKDIR="/tmp/rar2fs_installation"

    # Download rar2fs
    mkdir -p $WORKDIR
    cd $WORKDIR
    wget https://github.com/hasse69/rar2fs/archive/refs/tags/v$RAR2FS_VER.tar.gz
    tar zxvf v$RAR2FS_VER.tar.gz
    cd rar2fs-$RAR2FS_VER

    # Download unrar inside rar2fs directory
    wget http://www.rarlab.com/rar/unrarsrc-$UNRAR_VER.tar.gz
    tar zxvf unrarsrc-$UNRAR_VER.tar.gz
    cd unrar

    # Install unrar libraries, that's all rar2fs needs
    echo "Compiling unrar..."
    make --silent lib && echo "Unrar library compiled, installing..."
    make install-lib && echo "Unrar library installed successfully"

    # Back to rar2fs root directory
    cd ..

    # Install rar2fs
    echo "Compiling rar2fs..."
    autoreconf -f -i
    ./configure && make --silent && echo "rar2fs compiled successfully, installing..."
    make install && echo "rar2fs installed successfully"

    sed -i 's/#user_allow_other/user_allow_other/g' /etc/fuse.conf
    cd "$SCRIPT_PATH"
    rm -rf $WORKDIR
fi

# Check if Python is installed, and install it if not
if ! command_exists python3; then
    echo "Python not found. Installing Python..."
    apt-get install python3 -y
fi

if ! dpkg -l python3-venv | grep -q "venv module"; then
    echo "Python venv package not found. Installing..."
    apt-get install python3-venv -y
fi

# Create venv
echo "Creating python virtual environment..."
if [ -d "$VENV_PATH" ]; then
    if ! [ -f "$VENV_PATH/bin/python3" ]; then
        # Existing directory is NOT a virtual environment, aborting
        echo "Supplied virtual environment path conflicts with existing directory that is not a python virtual"\
        "environment, please select a different path for the virtual environment" >&2
        exit 1
    fi
    if ! $YES; then
        # Only ask for user warning confirmation if they didn't specify -y
        read -rp -n 1 "Warning: virtual environment already exists, continue? [y/n, default: n] : "
        if ! handle_reply "$REPLY" "Aborting install" true; then
            exit 1
        fi
    fi
else
    # Make venv
    python3 -m venv "$VENV_PATH"
fi

# Install Python packages
echo "Installing Python packages in $VENV_PATH virtual environment..."
"$VENV_PATH/bin/pip3" install --upgrade pip
"$VENV_PATH/bin/pip3" install -r requirements.txt

# Write virtual env path to venv.path
echo "$VENV_PATH" | tee venv.path > /dev/null
# Ensure user scripts are executable
chmod +x start.sh
chmod +x shutdown.sh
chmod +x upload.sh

echo "Initiating polar bear attack (do you guys actually read these messages?)"

# Call the Python script with the function name as an argument
echo "Initializing databases..."
# Does not need virtual environment since it is touching stuff outside of virtual environment

if "$VENV_PATH/bin/python3" utils/database_utils.py initialize_all_databases; then
    echo "Databases created successfully."
else
    echo "Error occurred while creating databases." >&2
    exit 1
fi

# SSL setup
if $USE_DOMAIN; then
    # Install Certbot and configure SSL with Let's Encrypt
        echo "Uninstalling any certbot instances installed via apt"
        if ! $YES; then
            read -rp -n 1 "Ready to uninstall any certbot instances installed from apt? [y/n, default n] : "
            if ! handle_reply "$REPLY" "User did not want to uninstall existing certbot, aborting" true; then
                exit 1
            fi
        fi

        apt-get remove -y certbot
        echo "Installing Certbot via pip..."
        apt-get install -y libaugeas0
        if ! [ -d "/opt/certbot" ]; then
            echo "Certbot virtual environment does not exist, creating now..."
            python3 -m venv /opt/certbot/
        fi
        /opt/certbot/bin/pip install --upgrade pip
        /opt/certbot/bin/pip install certbot certbot-nginx
        ln -sf /opt/certbot/bin/certbot /usr/bin/certbot

    echo "Configuring SSL with Let's Encrypt..."
    SSL_CERT_PATH="/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem"
    SSL_KEY_PATH="/etc/letsencrypt/live/$SERVER_NAME/privkey.pem"
    if [ -f "$SSL_CERT_PATH" ] && [ -f "$SSL_KEY_PATH" ]; then
        echo "Certificates already exist, existing certificates will be imported"
        echo "Calling certbot renew to ensure existing certificates are not expired"
        certbot renew -q
    else
        if ! $ARGS_USED; then
            read -rp -n 1 \
            "Would you like to use Cloudflare DNS challenge instead of the default HTTP challenge? [y/n, default n] : "
            if handle_reply "$REPLY" "Calling certbot for credentials using HTTP challenge..." false; then
                # User answered yes
                USE_CLOUDFLARE=true
                certbot_cf
            else
                # User answered no, just call certbot.
                certbot --nginx --agree-tos --register-unsafely-without-email --key-type ecdsa \
                --elliptic-curve secp384r1 -d "$SERVER_NAME"
            fi
        else
            # Args provided, use args to make decision
            if $USE_CLOUDFLARE; then
                certbot_cf
            else
                # No CF token provided, use HTTP challenge
                echo "Calling certbot for credentials using HTTP challenge..."
                certbot --nginx --agree-tos --register-unsafely-without-email --key-type ecdsa \
                --elliptic-curve secp384r1 -d "$SERVER_NAME"
            fi
        fi
    fi

    if ! $YES; then
        read -rp -n 1 \
        "SSL setup completed, set up automatic renewal and monthly certbot updates? [y/n, default y] : "
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # User entered yes or
            echo
            echo "Adding automatic renewal and monthly certbot updates to /etc/crontab if they don't already exist"
            add_auto_renewal
        elif [ -z "$REPLY" ]; then
            # User hit enter with no input or used -y arg
            echo "Adding automatic renewal and monthly certbot updates to /etc/crontab if they don't already exist"
            add_auto_renewal
        elif [[ $REPLY =~ ^[Nn]$ ]]; then
            echo
            echo "Not setting up automatic renewal, please be mindful of certificate expiry, especially if this"\
            "instance is exposed to the wide Internet"
        else
            echo
            echo "Invalid input. Only y/n are accepted (case insensitive)" >&2
            exit 1
        fi
    else
        # -y was specified, just add auto renewal
        echo "Adding automatic renewal and monthly certbot updates to /etc/crontab if they don't already exist"
        add_auto_renewal
    fi
else
    # Generate a self-signed certificate
    echo "Generating self-signed certificate..."
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:secp384r1 -keyout key.pem -out cert.pem -days 3650 -nodes \
    -subj "/CN=$SERVER_NAME" -addext "subjectAltName=DNS:$SERVER_NAME"

    # Move self-signed certificates to an appropriate directory (e.g., /etc/ssl)
    echo "Self-signed certificate generated, moving certificates to /etc/ssl from working directory"
    mv cert.pem /etc/ssl/certs/selfsigned_cert.pem
    mv key.pem /etc/ssl/private/selfsigned_key.pem

    # Update SSL paths in Flask app
    SSL_CERT_PATH="/etc/ssl/certs/selfsigned_cert.pem"
    SSL_KEY_PATH="/etc/ssl/private/selfsigned_key.pem"
    echo "Self-signed SSL certificate generation complete."
fi

# Update SSL paths in Flask app
sed -i "s|ssl_cert_path = .*|ssl_cert_path = '$SSL_CERT_PATH'|" app.py
sed -i "s|ssl_key_path = .*|ssl_key_path = '$SSL_KEY_PATH'|" app.py
echo "Your Flask app will now run with HTTPS!"

# Update the config.ini file with user, password, and port
echo "Updating config.ini hostname..."
sed -i "s/^hostname = .*/hostname = $SERVER_NAME/" config.ini

echo "Setup complete. Start web server by executing start.sh, and make your first upload with upload.sh!"
echo "Web app can be shutdown with shutdown.sh"
echo "Note: web app does not need to be running to upload, its usage is entirely optional"