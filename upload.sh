#!/bin/bash

print_help() {
    echo "Script usage: $SCRIPT_NAME \"folder/to/be/uploaded\" [OPTION]"
    echo "Directory name or full absolute directory path should be in double quotes, as shown above, to avoid" \
    "unexpected behavior."
    echo
    echo "Optional arguments:"
    echo "    -l, --ln: Hardlinks provided directory to DATADIR. If hardlink fails, fallback to symlink."
    echo
    echo "    -c, --cp: Copies provided directory to DATADIR."
    echo
    echo "    -m, --mv: Moves provided directory to DATADIR. May break other torrents that rely on the same data," \
    "use with caution."
    echo
    echo "    -h, --help: Show this help page."
}

SCRIPT_DATA_PATH=$( cd "$(dirname "${BASH_SOURCE[0]}")" || exit ; pwd -P )

cd "$SCRIPT_DATA_PATH" || exit

# # Only continue if config validator returns on fatal errors
if ! utils/config_validator.sh; then
    exit 1
fi

# Pretty colors
RED='\033[0;31m'
YLW='\033[1;33m'
NCL='\033[0m'

DATA_DIR="$(awk -F '=' '/^DATADIR[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2}' config.ini)"
# In case user put in a trailing forward slash to DATADIR
DATA_DIR=$(realpath -s "$DATA_DIR")
WATCH_DIR="$(awk -F '=' '/^WATCHFOLDER[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2}' config.ini)"
# In case user put in a trailing forward slash to DATADIR
WATCH_DIR=$(realpath -s "$WATCH_DIR")
DATA_PATH="$1"
FULL_SCRIPT_NAME="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_NAME="${FULL_SCRIPT_NAME##*/}"

# Initial argument check
if [ $# -eq 0 ] || [[ "$DATA_PATH" == "--help" ]] || [[ "$DATA_PATH" == "-h" ]]; then
    # No arguments provided or first argument was help, just print help
    print_help
    exit 0
fi

if [ $# -gt 2 ]; then
    echo -e "${RED}ERROR: Too many arguments provided${NCL}" >&2
    exit 1
fi

LN=false
CP=false
MV=false

if [ $# -gt 1 ]; then
    # Only bother parsing args if an arg beside path is specified
    if [ $# -gt 2 ]; then
        echo -e "${RED}ERROR: Too many args.${NCL}" >&2
        exit 1
    fi

    VALID_ARGS=("-h" "--help" "-l" "--ln" "-c" "--cp" "-m" "--mv")
    FOUND=false

    for item in "${VALID_ARGS[@]}"; do
        if [[ "$item" == "$2" ]]; then
            FOUND=true
            break
        fi
    done
    if ! $FOUND; then
        echo -e "${RED}Error: Unrecognized argument: $2${NCL}" >&2
        exit 1
    fi

    if ! OPTS=$(getopt -o 'hlcm' -l 'help,ln,cp,mv' -n "$SCRIPT_NAME" -- "$@"); then
        echo -e "${RED}ERROR: Failed to parse options. See --help.${NCL}" >&2
        exit 1
    fi
    # Reset the positional parameters to the parsed options
    eval set -- "$OPTS"

    # Process arguments
    while true; do
        case "$1" in
            -l | --ln)
                LN=true
                shift
                ;;
            -c | --cp)
                CP=true
                shift
                ;;
            -m | --mv)
                MV=true
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
                echo -e "${RED}ERROR: Unrecognized argument${NCL}" >&2
                echo "This might have been caused by the provided path containing special characters. See --help."
                exit 1
                ;;
        esac
    done
fi

# RW permissions check
if ! touch "$DATA_DIR/perm.test"; then
    echo -e "${RED}ERROR: User running script does not have write permissions to $DATA_DIR${NCL}" >&2
    exit 1
else
    # Cleanup
    rm "$DATA_DIR/perm.test"
fi

if ! touch "$WATCH_DIR/perm.test"; then
    echo -e "${RED}ERROR: User running script does not have write permissions to $WATCH_DIR${NCL}" >&2
    exit 1
else
    # Cleanup
    rm "$WATCH_DIR/perm.test"
fi

# Validate path input
if [[ "$DATA_PATH" != *"/"* ]]; then
    # A directory name was provided, assume rest of path is in DATADIR
    DATA_PATH="$DATA_DIR/$DATA_PATH"
elif [[ "$DATA_PATH" == /* ]]; then
    : # Don't do anything, already a full path. This is just to gate the else.
else
    echo -e "${RED}ERROR: only absolute paths or directory names are allowed: $DATA_PATH${NCL}" >&2
    exit 1
fi

DATA_PATH=$(realpath -s "$DATA_PATH")
if [ -f "$DATA_PATH" ]; then
    # It's a file. Error.
    echo -e "${RED}ERROR: $DATA_PATH is a file${NCL}" >&2
    exit 1
elif ! [ -d "$DATA_PATH" ]; then
    # There's no directory in DATADIR actually called what user provided
    # No need to check for file not existing, since if it was a file, above if catches
    # If file doesn't exist, -d will fail anyhow and thus be caught here.
    echo -e "${RED}ERROR: $DATA_PATH does not exist${NCL}" >&2
    exit 1
fi

UPLOADED_DIRECTORY="$(basename "$DATA_PATH")"
if ! [ -d "$DATA_DIR/$UPLOADED_DIRECTORY" ]; then
    # If this path doesn't already exit in DATADIR, it would have been already caught.
    # So this check functions as check for when users provide a path to data that is OUTSIDE of the DATADIR that doesn't
    # exist in DATADIR. If the data is already in DATADIR, no need to do anything

    # Data not already in DATADIR, clone/move it with the option provided
    echo "$UPLOADED_DIRECTORY not already in $DATA_DIR, creating it with specified option"
    if $LN; then
        # Hardlink, fallback to symlink otherwise
        if ! cp -alv --strip-trailing-slashes -t "$DATA_DIR" "$DATA_PATH"; then
            echo -e "${YLW}Could not hardlink, falling back to symlink${NCL}"
            ln -sv -t "$DATA_DIR" "$DATA_PATH" || exit 1
        fi
    elif $CP; then
        # Copy
        cp -av --strip-trailing-slashes -t "$DATA_DIR" "$DATA_PATH" || exit 1
    elif $MV; then
        mv -v --strip-trailing-slashes -t "$DATA_DIR" "$DATA_PATH" || exit 1
    else
        echo -e "${RED}ERROR: Cannot create data to upload. When providing a path that is outside of DATADIR," \
        "move, copy, or link MUST be specified.${NCL}" >&2
    fi
fi

# Run using venv
source "venv/bin/activate"

if python3 upload.py "$UPLOADED_DIRECTORY"; then
    exit 0;
else
    exit 1;
fi