#!/bin/sh
# Finds the local timezone from the printer's public IP once the network
# answers, for the touchscreen's clock. See config-docs/CREATOR5_CLOCK.md.
OC=/usr/data/opencreator
MANUAL=$OC/timezone
AUTO=$OC/timezone.auto
TABLE=$OC/startup/timezones.txt
CA=/opt/etc/ssl/certs/ca-certificates.crt

[ -s "$MANUAL" ] && exit 0

lookup() {
    zone=
    [ -s "$CA" ] && zone=$(curl -fsS -m 10 --cacert "$CA" https://ipapi.co/timezone 2>/dev/null)
    case $zone in */*) ;; *) zone=$(curl -fsS -m 10 'http://ip-api.com/line/?fields=timezone' 2>/dev/null) ;; esac
    case $zone in */*) echo "$zone" ;; esac
}

i=0
zone=
while [ "$i" -lt 30 ]; do
    zone=$(lookup)
    [ -n "$zone" ] && break
    i=$((i + 1))
    sleep 20
done
[ -n "$zone" ] || { echo "no timezone found"; exit 0; }

tz=$(awk -v z="$zone" '$1 == z { print $2; exit }' "$TABLE")
[ -n "$tz" ] || { echo "$zone is not in $TABLE"; exit 0; }
echo "$zone: $tz"
[ "$(cat "$AUTO" 2>/dev/null)" = "$tz" ] && exit 0
echo "$tz" > "$AUTO.tmp" && mv "$AUTO.tmp" "$AUTO"

# The screen read the old timezone when it started: restart it, unless a print
# runs. The launcher goes too, or it respawns the screen with its old one;
# 41-helixscreen.sh then starts it again.
state=$(curl -s -m 5 'http://127.0.0.1:7125/printer/objects/query?print_stats=state' 2>/dev/null)
case $state in
    *'"printing"'* | *'"paused"'*) ;;
    *)
        for p in $(ls /proc | grep '^[0-9]*$'); do
            case "$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)" in
                */helixscreen/bin/helix-launcher.sh* | /usr/data/helixscreen/bin/helix-watchdog* | \
                    /usr/data/helixscreen/bin/helix-screen*) kill "$p" 2>/dev/null ;;
            esac
        done
        ;;
esac
exit 0
