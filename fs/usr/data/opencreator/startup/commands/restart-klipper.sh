#!/bin/sh
# 10-klipper.sh starts Klipper again
status=1
for dir in /proc/[0-9]*; do
    if grep -q klippy.py "$dir/cmdline" 2>/dev/null; then
        kill "${dir#/proc/}" && status=0
    fi
done
exit $status
