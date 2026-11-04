#!/bin/sh
HELIX_DIR=/usr/data/helixscreen
[ -x "$HELIX_DIR/bin/helix-screen" ] || exit 0
# Static binaries; the stack's library path is not for them.
unset LD_LIBRARY_PATH

TOUCH=$(awk '
    /^N: Name=/ { name = tolower($0) }
    /^H: Handlers=/ && name ~ /goodix|touch/ {
        for (i = 2; i <= NF; i++)
            if ($i ~ /^event[0-9]+$/) { print "/dev/input/" $i; exit }
    }' /proc/bus/input/devices 2>/dev/null)
export HELIX_TOUCH_DEVICE=${TOUCH:-/dev/input/event2}
export HELIX_DISPLAY_BACKEND=fbdev HELIX_FB_DEVICE=/dev/fb0
# The panel is portrait; turned like GrumpyScreen's display_rotate: 1.
# A HELIX_DISPLAY_ROTATION line in config/helixscreen.env wins.
grep -q '^HELIX_DISPLAY_ROTATION=' "$HELIX_DIR/config/helixscreen.env" 2>/dev/null ||
    export HELIX_DISPLAY_ROTATION=90
export HELIX_LOG_DEST=file HELIX_LOG_FILE=/tmp/helixscreen.log
export HELIX_CACHE_DIR=$HELIX_DIR/cache
export HOME=${HOME:-/root}
mkdir -p "$HELIX_CACHE_DIR"

while true; do
    "$HELIX_DIR/bin/helix-launcher.sh" >> /tmp/helixscreen-launcher.log 2>&1
    sleep 3
done
