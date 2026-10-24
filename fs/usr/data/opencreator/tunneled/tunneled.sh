#!/bin/sh

# Based on original C5 Tunneled,

SCRIPTS=/usr/data/opencreator/startup/scripts
export LD_LIBRARY_PATH=/usr/prog/Python-3.8.2/lib:/usr/prog/openssl-1.0.2d/lib:/usr/prog/libffi-3.4.4/lib:$LD_LIBRARY_PATH
export PATH=$PATH:/opt/bin

# MCU firmware the installer left for this power-on, before the tunnel wakes the boards
[ ! -f /usr/data/opencreator/mcu-flash-pending/flash.sh ] ||
    sh /usr/data/opencreator/mcu-flash-pending/flash.sh > /tmp/mcu-flash-pending.log 2>&1

sh "$SCRIPTS/05-entfix.sh"
sh "$SCRIPTS/06-sftp.sh"
sh "$SCRIPTS/30-camera.sh" &
sh "$SCRIPTS/40-grumpyscreen.sh" &

while true; do
    /usr/prog/Python-3.8.2/bin/python3 /usr/prog/c5-tunnel-socat/c5_socat.py
    sleep 3
done
