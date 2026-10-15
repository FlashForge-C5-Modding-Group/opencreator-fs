#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
OC=/usr/data/opencreator/klipper
KPY=$OC/klippy-env/bin/python
export PATH=$PATH:/opt/bin

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

while true; do
    if [ -x "$KPY" ]; then
        log_launcher "Klippy is starting..."

        "$KPY" "$OC/klipper/klippy/klippy.py" "$OC/config/printer.cfg" -l "$OC/logs/printer.log" -a /tmp/uds

        log_launcher "Klippy exited; see $OC/logs/printer.log. Restarting in 3 s."
        log_launcher "ERR CODE 0 - Klippy"
    fi
    sleep 3
done
