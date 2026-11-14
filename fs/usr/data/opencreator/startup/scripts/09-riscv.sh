#!/bin/sh
# Runs the X2600's RISC-V core as Klipper's [mcu soc]: loads the Kalico image
# over the stock one and bridges it to /tmp/klipper_host_soc.
# See config-docs/CREATOR5_RISCV.md.

DIR=/usr/data/opencreator/rvmcu
LOG=/usr/data/logs/rvmcu.log
LOCK=/tmp/rvmcu.lock
LINK=/tmp/klipper_host_soc

exec 9>"$LOCK"
flock -n 9 || exit 0

log() {
    echo "$(date '+%F %T') $*" >> "$LOG"
}

# soc_mcu.ko is loaded by app_startup.sh
n=0
while [ ! -c /dev/mcu ] && [ $n -lt 30 ]; do
    sleep 1
    n=$((n + 1))
done
if [ ! -c /dev/mcu ]; then
    log "no /dev/mcu"
    exit 1
fi

chmod +x "$DIR/rvmcu"
if ! "$DIR/rvmcu" load "$DIR/x2600rv.bin" >> "$LOG" 2>&1; then
    log "load failed"
    exit 1
fi

while true; do
    log "bridge started"
    "$DIR/rvmcu" bridge "$LINK" >> "$LOG" 2>&1
    log "bridge exited ($?)"
    sleep 2
done
