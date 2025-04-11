check() {
    for REQUIRED_KEY in "${REQUIRED_KEYS[@]}"; do
        if [[ "$1" == "$REQUIRED_KEY" ]]; then
            if [[ -z "$2" ]]; then
                if [ "$1" == "APIKEY" ]; then
                    echo -e "${YLW}Warning${NCL}: TMDB API key not set, will not be able to get IMDB information"
                elif [ "$1" == "CLIENT_ID" ] || [ "$1" == "CLIENT_SECRET" ]; then
                    echo -e "${YLW}Warning${NCL}: IGDB $1 not set, will not be able to get video game information"
                elif [[ $2 == *"/" ]] || [[ $2 == *"/ " ]]; then
                    echo -e "${YLW}Warning${NCL}: $1 should not have a trailing forward slash ( '/' ), might introduce" \
                    "bugs."
                else
                    echo -e "${RED}Fatal${NCL}: $1 must not be empty"
                    FATAL_ERROR=true
                fi
            fi
        fi
    done
}

# Pretty colors
RED='\033[0;31m'
YLW='\033[1;33m'
NCL='\033[0m'

FULL_SCRIPT_NAME="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT_DIR="${FULL_SCRIPT_NAME%/*}/.."

# Keys that require user to set them
REQUIRED_KEYS=\
("DATADIR" "USERNAME" "PASSWORD" "LOGINTXT" "CAPTCHA_PASSKEY" "APIKEY" "CLIENT_ID" "CLIENT_SECRET" "HASHER" \
"SOURCEPATH" "WATCHFOLDER" "SITEURL" "ANNOUNCEURL")
FATAL_ERROR=false
while IFS= read -r LINE; do
    # Skip lines without an '=' sign
    [[ "$LINE" != *=* ]] && continue

    # Split into KEY and VALUE
    KEY="${LINE%%=*}"
    VALUE="${LINE#*=}"

    # Trim whitespace
    KEY="$(echo "$KEY" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    VALUE="$(echo "$VALUE" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"

    # Run the check
    check "$KEY" "$VALUE"
done < "$ROOT_DIR/config.ini"

if $FATAL_ERROR; then
    exit 1
else
    exit 0
fi