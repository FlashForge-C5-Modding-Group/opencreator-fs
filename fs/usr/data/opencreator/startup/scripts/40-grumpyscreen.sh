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

while true; do
    "$GRUMPY" >> /tmp/grumpyscreen.log 2>&1
    sleep 3
done
