#!/bin/sh
# Touchscreen backlight timeout, beside the screen app (it doesn't change it).
# Settings: screen-timeout.conf in the config folder. See
# config-docs/CREATOR5_SCREEN_TIMEOUT.md.
DAEMON=/usr/data/opencreator/screen-timeout/screen_timeout.py
[ -f "$DAEMON" ] || exit 0

PY=
for p in /usr/data/python-hf/bin/python3 /usr/data/opencreator/klipper/klippy-env/bin/python /opt/bin/python3; do
    if [ -x "$p" ]; then PY=$p; break; fi
done
[ -n "$PY" ] || exit 0

# Restart it if it stops; exit status 3 means there's nothing for it to do
# (already running, or no backlight)
while true; do
    "$PY" "$DAEMON"
    [ $? -eq 3 ] && exit 0
    sleep 5
done
