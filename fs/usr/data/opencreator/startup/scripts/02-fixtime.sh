#!/bin/sh
# The printer has no hardware clock: every boot starts at 1970. Put the clock
# back to the last saved time, set it from the network once that answers, and
# save it every 5 minutes. See config-docs/CREATOR5_CLOCK.md.
SAVED=/usr/data/opencreator/.clock

saved=$(cat "$SAVED" 2>/dev/null)
case $saved in ''|*[!0-9]*) saved=0 ;; esac
[ "$saved" -gt "$(date +%s)" ] && date -s "@$saved" >/dev/null 2>&1

sync_time() {
    rdate -s time.nist.gov >/dev/null 2>&1 && return 0
    # Networks that block the Time protocol (TCP 37) still pass HTTP
    for url in http://connectivitycheck.gstatic.com/generate_204 http://www.google.com; do
        hdr=$(curl -sI -m 6 "$url" 2>/dev/null | sed -n 's/^[Dd]ate: *//p' | tr -d '\r')
        [ -n "$hdr" ] || continue
        now=$(date -u -D '%a, %d %b %Y %H:%M:%S' -d "${hdr% GMT}" +%s 2>/dev/null) || continue
        date -u -s "@$now" >/dev/null 2>&1 && return 0
    done
    return 1
}

save_time() {
    date +%s > "$SAVED.tmp" && mv "$SAVED.tmp" "$SAVED"
}

(
    synced=0 last_sync=0 last_save=0
    while true; do
        now=$(date +%s)
        if [ "$synced" = 0 ] || [ $((now - last_sync)) -ge 3600 ]; then
            if sync_time; then
                synced=1
                now=$(date +%s)
                last_sync=$now
                save_time
                last_save=$now
            fi
        fi
        if [ $((now - last_save)) -ge 300 ]; then
            save_time
            last_save=$now
        fi
        sleep 10
    done
) &
