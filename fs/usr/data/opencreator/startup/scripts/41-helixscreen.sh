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

# The printer has no timezone: timezone (yours) or timezone.auto (04-timezone.sh)
# holds a POSIX TZ string or a zone name; read at every start of the screen.
OC=/usr/data/opencreator
screen_tz() {
    for f in "$OC/timezone" "$OC/timezone.auto"; do
        [ -s "$f" ] || continue
        v=$(head -n 1 "$f")
        case $v in */*) v=$(awk -v z="$v" '$1 == z { print $2; exit }' "$OC/startup/timezones.txt") ;; esac
        [ -n "$v" ] && { echo "$v"; return; }
    done
}

# Custom kernels can show boot messages on the screen (framebuffer console):
# hand the screen to the UI, or the console's text and cursor draw over it
for v in /sys/class/vtconsole/vtcon*; do
    grep -q "frame buffer" "$v/name" 2>/dev/null && echo 0 > "$v/bind"
done

while true; do
    TZ=$(screen_tz)
    if [ -n "$TZ" ]; then export TZ; else unset TZ; fi
    "$HELIX_DIR/bin/helix-launcher.sh" >> /tmp/helixscreen-launcher.log 2>&1
    sleep 3
done
