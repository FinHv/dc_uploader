#!/bin/bash
VENV_PATH=/opt/dcc-uploader

SCRIPT_PATH=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )

cd "$SCRIPT_PATH"

screen -dmS dcc-uploader "$VENV_PATH/bin/python3" app.py