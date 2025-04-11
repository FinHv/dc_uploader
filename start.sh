#!/bin/bash

script_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" || exit ; pwd -P )

cd "$script_path" || exit

if utils/config_validator.sh "start.sh"; then
    # Only start if config validator returns on fatal errors
    echo "Starting web app with detached screen named \"dc-uploader\""
    screen -dmS dc-uploader "venv/bin/python3" app.py
fi