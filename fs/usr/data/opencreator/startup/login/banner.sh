#!/bin/sh
# OpenCreator login banner (see config-docs/CREATOR5_LOGIN.md)

if [ -t 1 ]; then
    E=$(printf '\033')
    B="$E[1m" D="$E[2m" C="$E[36m" W="$E[97m" R="$E[0m"
else
    B= D= C= W= R=
fi

up=$(cut -d. -f1 /proc/uptime)
d=$((up / 86400)) h=$((up % 86400 / 3600)) m=$((up % 3600 / 60))
if [ "$d" -gt 0 ]; then uptime="${d}d ${h}h ${m}m"
elif [ "$h" -gt 0 ]; then uptime="${h}h ${m}m"
else uptime="${m}m"; fi

ips=$(ip -4 -o addr 2>/dev/null | awk '$2 != "lo" {split($4, a, "/"); printf "%s%s (%s)", s, a[1], $2; s = ", "}')
[ -n "$ips" ] || ips="not connected"

storage=$(df -Pk /usr/data 2>/dev/null | awk 'NR == 2 {printf "%.1f GB free of %.1f GB", $4 / 1048576, $2 / 1048576}')

machine=$(sed -n 's/^[[:space:]]*MACHINE=\([A-Za-z0-9]*\).*/\1/p' \
    /usr/prog/app_startup.sh /usr/prog/PROGRAM/runFirmwareExe.sh 2>/dev/null | head -n 1)
case $machine in
    Creator5Pro) model="Creator 5 Pro" ;;
    Creator5) model="Creator 5" ;;
    *) model="Creator 5 series" ;;
esac

plugins=
if [ -f /usr/data/opencreator/plugin-manager/oc_plugin.py ]; then
    n=0
    for d in /usr/data/opencreator/plugins/*/; do
        [ -f "$d/opencreator-plugin.json" ] || ls "$d"*.cfg "$d"en/*.cfg >/dev/null 2>&1 && n=$((n + 1))
    done
    case $n in
        0) plugins="none installed (oc-plugin search)" ;;
        1) plugins="1 installed (oc-plugin list)" ;;
        *) plugins="$n installed (oc-plugin list)" ;;
    esac
fi

I2="${B}OpenCreator${R}"
I3="${D}-----------${R}"
I4="${C}Uptime${R}   $uptime"
I5="${C}IP${R}       $ips"
I6="${C}Storage${R}  $storage in /usr/data"
I7="${C}Host${R}     $(hostname)"
[ -n "$plugins" ] && I8="${C}Plugins${R}  $plugins"

echo
i=1
while IFS= read -r line; do
    eval "info=\${I$i:-}"
    printf ' %s%s%s   %s\n' "$W" "${line%"|"}" "$R" "$info"
    i=$((i + 1))
done <<'LOGO'
       ▄▄▄▄▄▄▄▄      ▄▄▄▄▄▄▄▄▄      |
   ▗▟████████████▙▞▜███████████▄    |
  ▟██▛▘        ▝▜██▙▝       ▝▜███▄  |
 ▐██▌            ███▌               |
 ▐██▌            ███▌               |
 ▐██▌            ███▌               |
 ▐██▙▖           ▜██▙        ▄▄▄▄▖  |
  ▝▜█████████████▄▀████████████▀    |
     ▝▀▀▀▀▀▀▀▀▀▀     ▀▀▀▀▀▀▀▀▀      |
LOGO
pad=$(( (36 - ${#model}) / 2 + 1 ))
printf "%${pad}s%s%s%s\n\n" "" "$B" "$model" "$R"
