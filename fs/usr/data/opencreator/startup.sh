#!/bin/sh
# A more advanced version of LoopScript from OpenCreator Legacy
# Credits to https://github.com/FlashForge-C5-Modding-Group/Creator-5-Scripts/graphs/contributors
set -e
set -u

TARGET_DIR="/usr/data/opencreator/scripts"
LAUNCHER_LOG="/tmp/opencreator.log"

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

if [ ! -d "$TARGET_DIR" ]; then
    log_launcher "Error: Directory $TARGET_DIR does not exist."
    exit 1
fi

for script in $(ls "$TARGET_DIR"/*.sh 2>/dev/null | sort); do
    if [ -f "$script" ]; then

        script_name=$(basename "$script")
        log_file="/tmp/${script_name}.log"

        if [ -x "$script" ]; then
            EXEC_TYPE="has +x"
        else
            EXEC_TYPE="missing +x"
        fi

        log_launcher "Launched: $script_name ($EXEC_TYPE)"

        ( echo "=== Executed via sh ($EXEC_TYPE) ==="; sh "$script" ) > "$log_file" 2>&1 &
    fi
done