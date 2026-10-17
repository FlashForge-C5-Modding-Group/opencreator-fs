#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
OC=/usr/data/opencreator/klipper
MOONRAKER=/usr/prog/moonraker/moonraker
MPY=/usr/prog/moonraker/moonraker-env/bin/python
export PATH=$PATH:/opt/bin
# pip (Moonraker's update manager) builds zeroconf as plain Python, finds
# python-hf's zlib/libjpeg for Pillow through CFLAGS/LDFLAGS, and keeps its
# own cache: Entware's soft-float wheels carry the same tag.
export SKIP_CYTHON=1 CFLAGS="-I/usr/data/python-hf/include" LDFLAGS="-L/usr/data/python-hf/lib"
export PIP_CACHE_DIR=/usr/data/opencreator/home/.cache/pip-hf
# HOME is the read-only / at boot; Moonraker's update manager runs pip.
if [ -z "${HOME:-}" ] || [ "$HOME" = / ]; then
    export HOME=/usr/data/opencreator/home
    mkdir -p "$HOME"
fi

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

for component in opencreator_3mf opencreator_machine; do
    ln -sf "/usr/data/opencreator/moonraker/$component.py" \
        "$MOONRAKER/moonraker/components/$component.py"
    grep -q "^\[$component\]" "$OC/config/moonraker.conf" ||
        printf '\n[%s]\n' "$component" >> "$OC/config/moonraker.conf"
done
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
