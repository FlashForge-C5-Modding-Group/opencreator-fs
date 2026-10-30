#!/bin/sh
GRUMPY=/usr/data/grumpyscreen/grumpyscreen
[ -x "$GRUMPY" ] || exit 0

TOUCH=$(awk '
    /^N: Name=/ { name = tolower($0) }
    /^H: Handlers=/ && name ~ /goodix|touch/ {
        for (i = 2; i <= NF; i++)
            if ($i ~ /^event[0-9]+$/) { print "/dev/input/" $i; exit }
    }' /proc/bus/input/devices 2>/dev/null)
export LVGL_EVDEV_DEV=${TOUCH:-/dev/input/event2}

# The config folder's copy wins, so it can be edited from Fluidd or Mainsail.
# A tunneled SoC has no config folder and keeps the one next to the binary.
CONFIG_DIR=/usr/data/opencreator/klipper/config
CONFIG=$CONFIG_DIR/grumpyscreen.cfg
if [ -d "$CONFIG_DIR" ]; then
    [ -f "$CONFIG" ] || cp "${GRUMPY}.cfg" "$CONFIG"
    [ -f "$CONFIG" ] && export CONFIG_FILE="$CONFIG"
fi

while true; do
    "$GRUMPY" >> /tmp/grumpyscreen.log 2>&1
    sleep 3
done
