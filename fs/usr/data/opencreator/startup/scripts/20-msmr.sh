#!/bin/sh
export LD_LIBRARY_PATH="/usr/prog/Python-3.8.2/lib:${LD_LIBRARY_PATH:-}"
LAUNCHER_LOG="/tmp/opencreator.log"

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

log_launcher "Launching Moonraker..."
/usr/prog/klipper/moonrakerDaemon start &
log_launcher "Launching WebUI..."
/usr/prog/nginx/sbin/nginx -p /usr/prog/nginx -c /usr/prog/nginx/conf/nginx.conf

log_launcher "If you see this, there's something wrong, but only Moonraker & or any WebUI is broken"
log_launcher "ERR CODE 1 - nginx"
