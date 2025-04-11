#!/bin/bash

print_help() {
    echo "Script usage: $script_name [QUEUE FILE] [OPTION]"
    echo "Queue file can either be a full absolute path or a relative path relative to $script_name. e.g." \
    "$script_name some_queue_file.txt [OPTION] if queue file is located in the same folder as $script_name"
    echo
    echo "Required argument. Pick one:"
    echo "    -l, --ln: Hardlinks provided directory to DATADIR. If hardlink fails, fallback to symlink."
    echo
    echo "    -c, --cp: Copies provided directory to DATADIR."
    echo
    echo "    -m, --mv: Moves provided directory to DATADIR. May break other torrents that rely on the same data," \
    "use with caution."
    echo
    echo "    -h, --help: Show this help page."
}

script_data_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" || exit ; pwd -P )

cd "$script_data_path" || exit

# # Only continue if config validator returns on fatal errors
if ! utils/config_validator.sh; then
    exit 1
fi

# Pretty colors
red='\033[0;31m'
ncl='\033[0m'

data_dir="$(awk -F '=' '/^DATADIR[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2}' config.ini)"
# In case user put in a trailing forward slash to DATADIR
data_dir=$(realpath -s "$data_dir")
queue_file="$1"
full_script_path="$(readlink -f "${BASH_SOURCE[0]}")"
script_name="${full_script_path##*/}"

# Initial argument check
if [ $# -eq 0 ] || [[ "$queue_file" == "--help" ]] || [[ "$queue_file" == "-h" ]]; then
    # No arguments provided or first argument was help, just print help
    print_help
    exit 0
fi

if [ $# -lt 2 ]; then
    echo -e "${red}ERROR: Not enough arguments provided${ncl}" >&2
    exit 1
fi

if [ $# -gt 2 ]; then
    echo -e "${red}ERROR: Too many args.${ncl}" >&2
    exit 1
fi

valid_args=("-h" "--help" "-l" "--ln" "-c" "--cp" "-m" "--mv")
found=false

for item in "${valid_args[@]}"; do
    if [[ "$item" == "$2" ]]; then
        found=true
        break
    fi
done
if ! $found; then
    echo -e "${red}Error: Unrecognized argument: $2${ncl}" >&2
    exit 1
fi

# Store arg so it's not lost after getopt
ARG="$2"

if ! opts=$(getopt -o 'hlcm' -l 'help,ln,cp,mv' -n "$script_name" -- "$@"); then
    echo -e "${red}ERROR: Failed to parse options. See --help.${ncl}" >&2
    exit 1
fi
# Reset the positional parameters to the parsed options
eval set -- "$opts"

# Process arguments
while true; do
    case "$1" in
        -l | --ln)
            shift
            ;;
        -c | --cp)
            shift
            ;;
        -m | --mv)
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
            echo -e "${red}ERROR: Unrecognized argument${ncl}" >&2
            exit 1
            ;;
    esac
done

eval set -- "$opts"
queue_file=$(realpath -s "$queue_file")
if ! [ -f "$queue_file" ]; then
    # It's a file. Error.
    echo -e "${red}ERROR: $queue_file does not exist${ncl}" >&2
    exit 1
fi

# Remove old log file
log_path="files/queue_upload.log"
if [ -f "$log_path" ]; then
    rm "$log_path"
fi

while IFS= read -r line; do
    if ./upload.sh "$line" "$ARG"; then
        echo "Successfully uploaded: $(basename "$line")" >> "$log_path"
    else
        echo "Error when uploading: $(basename "$line")" >> "$log_path"
    fi
done < "$queue_file"