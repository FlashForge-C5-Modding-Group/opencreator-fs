#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
OC=/usr/data/opencreator/klipper
MOONRAKER=/usr/prog/moonraker/moonraker
MPY=/usr/prog/moonraker/moonraker-env/bin/python
export PATH=$PATH:/opt/bin

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

ln -sf /usr/data/opencreator/moonraker/opencreator_3mf.py \
    "$MOONRAKER/moonraker/components/opencreator_3mf.py"
grep -q '^\[opencreator_3mf\]' "$OC/config/moonraker.conf" ||
    printf '\n[opencreator_3mf]\n' >> "$OC/config/moonraker.conf"
[ -e "$OC/gcodes" ] || [ -L "$OC/gcodes" ] || ln -s /usr/data/gcodes "$OC/gcodes"
mkdir -p "$OC/tmp"

log_launcher "Launching WebUI..."
/usr/prog/nginx/sbin/nginx -p /usr/prog/nginx -c /usr/prog/nginx/conf/nginx.conf

while true; do
    if [ -x "$MPY" ]; then
        log_launcher "Launching Moonraker..."
        rm -rf "$OC/tmp"/*
        TMPDIR="$OC/tmp" "$MPY" "$MOONRAKER/moonraker/moonraker.py" -d "$OC"
        log_launcher "Moonraker exited; restarting in 3 s."
        log_launcher "ERR CODE 1 - Moonraker"
    fi
    sleep 3
done
