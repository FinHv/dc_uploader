#!/bin/bash
echo "Gracefully shutting down uploader"

screen -S dcc-uploader -X stuff $'\003'
