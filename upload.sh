#!/bin/bash

print_help() {
    echo "Script usage: upload.sh \"/full/path/to/torrent/directory\" [OPTION]"
    echo "Optional arguments:"
    echo "-l, --link: Hardlinks provided directory to DATADIR. If hardlink fails, fallback to symlink."
    echo
    echo "-c, --copy: Copies provided directory to DATADIR"
    echo
    echo "-m, --move: Moves provided directory to DATADIR"
    exit 0
}

# Initial argument check
if [ $# -eq 0 ] || [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    # No arguments provided or first argument was help, just print help
    print_help
fi

if [ $# -gt 2 ]; then
    echo "Too many arguments provided" >&2
    exit 1
fi

if ! [ -d "$1" ] && ! [ -f "$1" ]; then
    # Provided path does not resolve to an existing file or directory
    echo "Provided directory or file does not exist. Remember, the first argument MUST be the valid path of the data to be uploaded" >&2
    exit 1
fi

DATA_PATH=$1
LN=false
CP=false
MV=false

if [ -n "$2" ]; then
    # Only bother parsing args if an arg beside path is specified
    if ! OPTS=$(getopt -o 'hlcm' -l 'help,link,copy,move' -n 'upload.sh' -- "$@"); then
        echo "Failed to parse options" >&2
        exit 1
    fi
    # Reset the positional parameters to the parsed options
    eval set -- "$OPTS"

    # Process arguments
    while true; do
        case "$1" in
            -l | --link)
                LN=true
                shift
                ;;
            -c | --copy)
                CP=true
                shift
                ;;
            -m | --move)
                MV=true
                shift
                ;;
            -h | --help)
                print_help
                ;;
            --)
                shift
                break
                ;;
            *)
                echo "Unrecognized argument" >&2
                exit 1
                ;;
        esac
    done
fi

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or with sudo" >&2
    #exit 1
fi

SCRIPT_DATA_PATH=$( cd "$(dirname "${BASH_SOURCE[0]}")" || exit ; pwd -P )

cd "$SCRIPT_DATA_PATH" || exit

VENV_DATA_PATH=$(head -n 1 venv.path)

# Run using venv
source "$VENV_DATA_PATH/bin/activate"

"$VENV_DATA_PATH/bin/python3" upload.py $1