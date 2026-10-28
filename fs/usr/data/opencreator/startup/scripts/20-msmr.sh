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

# The stock site gives the API location 600 s; large uploads and copies need
# more (see /usr/data/nginx/conf.d/creator5-timeouts.conf).
SITE=/usr/data/nginx/sites-available/mainsail
grep -q 'proxy_read_timeout 600;' "$SITE" 2>/dev/null &&
    sed -i 's/proxy_read_timeout 600;/proxy_read_timeout 3600;/' "$SITE"
# Cameras: nginx redirects to mjpg-streamer's own port instead of relaying
# every frame (see config-docs/CREATOR5_CPU_PRIORITY.md). This nginx has no
# rewrite module: the redirect is the 404 of a root that doesn't exist.
for n in 1 2 3 4; do
    grep -q "proxy_pass http://mjpgstreamer$n/;" "$SITE" 2>/dev/null &&
        sed -i "s#proxy_pass http://mjpgstreamer$n/;#root /nonexistent; error_page 403 404 =302 http://\$host:$((8079 + n))/\$is_args\$args;#" "$SITE"
done
# Sites without a camera location (new installs) get the same redirect for
# the default camera, so the relative /webcam/ URL in moonraker.conf works.
if [ -f "$SITE" ] && ! grep -q 'location /webcam' "$SITE"; then
    awk '
        !done && /^[[:space:]]*server[[:space:]]*\{/ {
            print
            print "    location /webcam/ { root /nonexistent; error_page 403 404 =302 http://$host:8080/$is_args$args; }"
            done = 1
            next
        }
        { print }
    ' "$SITE" > "$SITE.tmp" && mv "$SITE.tmp" "$SITE"
fi

log_launcher "Launching WebUI..."
/usr/prog/nginx/sbin/nginx -p /usr/prog/nginx -c /usr/prog/nginx/conf/nginx.conf

while true; do
    if [ -x "$MPY" ]; then
        [ -f /usr/data/opencreator/plugin-manager/oc-plugin ] &&
            sh /usr/data/opencreator/plugin-manager/oc-plugin sync --only moonraker >> "$LAUNCHER_LOG" 2>&1
        log_launcher "Launching Moonraker..."
        rm -rf "$OC/tmp"/*
        TMPDIR="$OC/tmp" "$MPY" "$MOONRAKER/moonraker/moonraker.py" -d "$OC"
        log_launcher "Moonraker exited; restarting in 3 s."
        log_launcher "ERR CODE 1 - Moonraker"
    fi
    sleep 3
done
