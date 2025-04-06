#!/bin/bash

set -e

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

if [ "$EUID" -ne 0 ]
    then echo "Please run as root or with sudo"
    exit 1
fi

# Move to install.sh root directory
SCRIPT_PATH=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )

cd "$SCRIPT_PATH"

SERVER_NAME=$(hostname -f)

# Prompt for user, password, and port
read -p "Enter the port number for Flask to run on (default: 5000): " PORT
read -p "Enter the username for the Flask login (default: admin): " USER
read -p "Enter the password for the Flask login (default: p@ssw0rd) : " PASSWORD
read -p "Enter the path for the python virtual environment. Do not include trailing '/' (default: /opt/dcc-uploader) : " VENV_PATH
# Ask user if they want to use a domain or a self-signed certificate
read -p "Do you want to use a domain with Let's Encrypt? (y/n): " USE_DOMAIN

if [ "$USE_DOMAIN" == "y" ] || [ "$USE_DOMAIN" == "Y" ]; then
    # User chooses to use a domain
    echo "Info: If Let's Encrypt certificate for domain already exists, it will be imported instead of creating a new certificate"
    read -p "Enter the fully qualified domain name for the server for Let's Encrypt : " SERVER_NAME
    if [ -z "$SERVER_NAME" ] || [[ "$SERVER_NAME" == *" "* ]]; then
        echo "You must provide a valid domain name with no spaces for Let's Encrypt."
        exit 1
    fi
else
    # User chooses to use a self-signed certificate
    SERVER_NAME=$(hostname -f)
    echo "Using self-signed certificate for server name: $SERVER_NAME"
fi

# Set default values if not provided
PORT=${PORT:-5000}
USER=${USER:-admin}
PASSWORD=${PASSWORD:-p@ssw0rd}
VENV_PATH=${VENV_PATH:-/opt/dcc-uploader}

# Update the config.ini file with user, password, and port
echo "Updating config.ini..."
sed -i "s/^user = .*/user = $USER/" config.ini
sed -i "s/^password = .*/password = $PASSWORD/" config.ini
sed -i "s/^port = .*/port = $PORT/" config.ini
sed -i "s/^hostname = .*/hostname = $SERVER_NAME/" config.ini

# Install software-properties-common without user interaction
apt update
apt-get install software-properties-common -y

# Add the PPA repository without requiring confirmation
add-apt-repository -y ppa:wahibre/mtn

# Update package lists
apt update

# Install mtn, mediainfo, libfuse-dev, and unrar in one go
echo "Installing required tools and their dependencies..."
apt-get install build-essential mtn mediainfo libfuse-dev unrar screen -y

# Install rar2fs
if [[ ! -f /usr/local/bin/rar2fs ]]; then
    echo "Installing rar2fs..."
    UNRARVER="6.0.7"
    RAR2FSVER="1.29.3"
    WORKDIR="/tmp/rar2fs_installation"

    mkdir -p $WORKDIR
    cd $WORKDIR

    wget http://www.rarlab.com/rar/unrarsrc-$UNRARVER.tar.gz
    tar zxvf unrarsrc-$UNRARVER.tar.gz
    cd unrar
    make && make install
    make lib && make install-lib
    cd ..

    wget https://github.com/hasse69/rar2fs/releases/download/v$RAR2FSVER/rar2fs-$RAR2FSVER.tar.gz
    tar zxvf rar2fs-$RAR2FSVER.tar.gz
    cd rar2fs-$RAR2FSVER
    ./configure --with-unrar=../unrar --with-unrar-lib=/usr/lib/
    make && make install

    sed -i 's/#user_allow_other/user_allow_other/g' /etc/fuse.conf
    cd ~
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
echo "Creating python virtaul environment..."
if [ -d "$VENV_PATH" ]; then
    if ! [ -f "$VENV_PATH/bin/python3" ]; then
        # Existing directory is NOT a virtual environment, aborting
        echo "Supplied virtual environment path conflicts with existing directory that is not a python virtual environment, please select a different path for the virtual enviornment"
        exit 1
    fi
    read -p "Warning: virtual environment already exists, continue? [y/n] : " -r
    echo # Move to new line for cleaner look
    if ! [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting install"
        exit 1
    fi
else
    python3 -m venv $VENV_PATH
    echo "Ensuring $VENV_PATH virtual environment pip is up to date"
    "$VENV_PATH/bin/pip3" install --upgrade pip
fi

# Install Python packages
echo "Installing Python packages in $VENV_PATH virtual environment..."
"$VENV_PATH/bin/pip3" install requests rfr
"$VENV_PATH/bin/pip3" install flask
"$VENV_PATH/bin/pip3" install watchdog
"$VENV_PATH/bin/pip3" install torf-cli
"$VENV_PATH/bin/pip3" install gevent

# Overwrite contents of start script with start command
/usr/bin/printf "#!/bin/bash\nVENV_PATH=$VENV_PATH\n\nSCRIPT_PATH=\$( cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" ; pwd -P )\n\ncd \"\$SCRIPT_PATH\"\n\nscreen -dmS dcc-uploader \"\$VENV_PATH/bin/python3\" app.py" | tee start.sh > /dev/null
# Ensure start and shutdown scripts are executable
chmod +x start.sh
chmod +x shutdown.sh

# Call the Python script with the function name as an argument
echo "Initializing databases..."
# Does not need virtual environment since it is touching stuff outside of virtual environment
python3 utils/database_utils.py initialize_all_databases

if [ $? -eq 0 ]; then
    echo "Databases created successfully."
else
    echo "Error occurred while creating databases."
    exit 1
fi

# SSL setup
if [ "$USE_DOMAIN" == "y" ] || [ "$USE_DOMAIN" == "Y" ]; then
    # Install Certbot and configure SSL with Let's Encrypt
        echo "Uninstalling any certbot instances installed via apt"
        read -p "Ready to uninstall any certbot instances installed from apt? [y/n] : " -r
        echo
        if ! [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "User did not want to uninstall existing certbot, aborting"
            exit 1
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
    if [ -f $SSL_CERT_PATH ] && [ -f $SSL_KEY_PATH ]; then
        echo "Certificates already exist, existing certificates will be imported"
        echo "Calling certbot renew to ensure existing certificates are not expired"
        certbot renew -q
    else
        read -p "Would you like to use Cloudflare DNS challenge instead of the default HTTP challenge? [y/n] : " -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [ -f "/root/.secrets/cloudflare.ini" ]; then
                echo "Cloudflare credentials already exist, reusing existing credentials"
            else
                read -p "Cloudflare API token : " CF_TOKEN
                if [ -z "$CF_TOKEN" ]; then
                    echo "No Cloudflare token supplied, cannot continue"
                    exit 1
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
            echo "Calling certbot for credentials..."
            certbot certonly --agree-tos --register-unsafely-without-email --key-type ecdsa --elliptic-curve secp384r1 --dns-cloudflare --dns-cloudflare-credentials /root/.secrets/cloudflare.ini -d "$SERVER_NAME"
	    else
	        echo "Calling certbot for credentials..."
            certbot --nginx --agree-tos --register-unsafely-without-email --key-type ecdsa --elliptic-curve secp384r1 -d "$SERVER_NAME"
        fi
    fi

    # Update SSL paths in Flask app
    sed -i "s|ssl_cert_path = .*|ssl_cert_path = '$SSL_CERT_PATH'|" app.py
    sed -i "s|ssl_key_path = .*|ssl_key_path = '$SSL_KEY_PATH'|" app.py
    read -p "SSL setup completed using Let's Encrypt, set up automatic renewal and monthly certbot updates? [y/n] : " -r
    echo # Move to new line for cleaner look
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Adding automatic renewal and monthly certbot updates to /etc/crontab if they don't already exist"
        # Adds renewal to cron
        if ! cat /etc/crontab | grep -q "certbot renew -q"; then
            # At 12AM and 12PM every day. Will only renew certificates if eligible for automatic renewal
            echo "0 0,12 * * * root /opt/certbot/bin/python -c 'import random; import time; time.sleep(random.random() * 3600)' && sudo certbot renew -q" | tee -a /etc/crontab > /dev/null
        fi
        if ! cat /etc/crontab | grep -q "/opt/certbot/bin/pip install --upgrade certbot"; then
            # At 8am on the first day of the month
	        echo "0 8 1 * * root /opt/certbot/bin/pip install --upgrade certbot" | tee -a /etc/crontab > /dev/null
        fi
    else
        echo "Not setting up automatic renewal, please be mindful of certificate expiry, especially if this instance is exposed to the wide Internet"
    fi
else
    # Generate a self-signed certificate
    echo "Generating self-signed certificate..."
    openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=$SERVER_NAME"

    # Move self-signed certificates to an appropriate directory (e.g., /etc/ssl)
    mv cert.pem /etc/ssl/certs/selfsigned_cert.pem
    mv key.pem /etc/ssl/private/selfsigned_key.pem

    # Update SSL paths in Flask app
    SSL_CERT_PATH="/etc/ssl/certs/selfsigned_cert.pem"
    SSL_KEY_PATH="/etc/ssl/private/selfsigned_key.pem"
    sed -i "s|ssl_cert_path = .*|ssl_cert_path = '$SSL_CERT_PATH'|" app.py
    sed -i "s|ssl_key_path = .*|ssl_key_path = '$SSL_KEY_PATH'|" app.py
    echo "SSL setup complete using a self-signed certificate."
fi

echo "Your Flask app will now run with HTTPS!"

