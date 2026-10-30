#!/bin/sh
# 10-klipper.sh starts Klipper again
pids=$(ps w | awk '/klippy\.py/ && !/awk/ {print $1}')
[ -n "$pids" ] || exit 1
kill $pids
