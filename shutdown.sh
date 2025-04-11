#!/bin/bash
echo "Gracefully shutting down dc-uploader"

screen -S dc-uploader -X stuff $'\003'