#!/bin/sh
# The printer has no hardware clock: every boot starts at 1970. Put the clock
# back to the last saved time, set it from the network once that answers, and
# save it every 5 minutes. See config-docs/CREATOR5_CLOCK.md.
SAVED=/usr/data/opencreator/.clock

saved=$(cat "$SAVED" 2>/dev/null)
case $saved in ''|*[!0-9]*) saved=0 ;; esac
[ "$saved" -gt "$(date +%s)" ] && date -s "@$saved" >/dev/null 2>&1

NTP_SERVERS="pool.ntp.org time.google.com time.cloudflare.com time.apple.com
time.windows.com 0.pool.ntp.org 1.pool.ntp.org ntp.aliyun.com ntp.tencent.com
time.nist.gov"
RDATE_SERVERS="time.nist.gov time-a-g.nist.gov time-b-g.nist.gov time-a-wwv.nist.gov"

DATE_URLS="http://connectivitycheck.gstatic.com/generate_204 http://www.google.com
http://bin.entware.net/ http://github.com/ http://www.cloudflare.com/
http://www.baidu.com/ http://www.microsoft.com/"
RACE=/tmp/oc-fixtime

# Wait until an attempt has written $RACE/ok, every attempt (the arguments)
# has ended, or 8 s pass; then stop the rest. busybox ntpd -q retries forever
# when port 123 is silently dropped.
race() {
    i=0
    while [ "$i" -lt 32 ] && [ ! -s "$RACE/ok" ]; do
        alive=
        for pid in "$@"; do kill -0 "$pid" 2>/dev/null && { alive=1; break; }; done
        [ -n "$alive" ] || break
        sleep 0.25 2>/dev/null || sleep 1
        i=$((i + 1))
    done
    cat "$RACE"/pid.* 2>/dev/null | xargs kill 2>/dev/null
    kill "$@" 2>/dev/null
    rm -f "$RACE"/pid.*
    [ -s "$RACE/ok" ]
}

# Every time server at once, then every web server's Date header at once
sync_time() {
    rm -rf "$RACE"; mkdir -p "$RACE"
    n=0 pids=
    for server in $NTP_SERVERS; do
        n=$((n + 1))
        ( busybox ntpd -n -q -p "$server" >/dev/null 2>&1 & echo $! > "$RACE/pid.$n"
          wait $! && echo ntp >> "$RACE/ok" ) 2>/dev/null &
        pids="$pids $!"
    done
    for server in $RDATE_SERVERS; do
        n=$((n + 1))
        ( rdate -s "$server" >/dev/null 2>&1 & echo $! > "$RACE/pid.$n"
          wait $! && echo rdate >> "$RACE/ok" ) 2>/dev/null &
        pids="$pids $!"
    done
    race $pids && { rm -rf "$RACE"; return 0; }
    # Networks that block NTP (UDP 123) and the Time protocol (TCP 37) still pass HTTP
    pids=
    for url in $DATE_URLS; do
        ( hdr=$(curl -sI -m 6 "$url" 2>/dev/null | sed -n 's/^[Dd]ate: *//p' | tr -d '\r')
          now=$(date -u -D '%a, %d %b %Y %H:%M:%S' -d "${hdr% GMT}" +%s 2>/dev/null) &&
              [ -n "$hdr" ] && echo "$now" >> "$RACE/ok" ) 2>/dev/null &
        pids="$pids $!"
    done
    if race $pids; then
        now=$(head -n 1 "$RACE/ok")
        rm -rf "$RACE"
        date -u -s "@$now" >/dev/null 2>&1
        return
    fi
    rm -rf "$RACE"
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
