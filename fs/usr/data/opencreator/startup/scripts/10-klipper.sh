#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

log_launcher "Klippy is starting..."

/opt/bin/python3 /usr/prog/klipper/klippy/klippy.py /usr/data/config/printer.cfg -l /usr/data/logs/printer.log -a /tmp/uds

log_launcher "If you see this, there's something seriously wrong! Consult printer.log or launch it manually via || /opt/bin/python3 /usr/prog/klipper/klippy/klippy.py /usr/data/config/printer.cfg -l /usr/data/logs/printer.log -a /tmp/uds || This is a warning that there's something SERIOUSLY WRONG and Klippy has not started properly!"
log_launcher "ERR CODE 0 - Klippy"
