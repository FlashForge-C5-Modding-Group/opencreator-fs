#!/bin/sh
# USB Ethernet adapters: the printer has Wi-Fi only and no USB network
# drivers. Loads the modules in ../usb-ethernet, gives any adapter that
# appears an address by DHCP, and prefers it over Wi-Fi while it's connected.
# See config-docs/CREATOR5_USB_ETHERNET.md.
DIR=/usr/data/opencreator/startup/usb-ethernet
LOG=/usr/data/logs/usb-ethernet.log
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# Only the kernels these modules were built and checked for
kernel=$(ls /usr/prog/PROGRAM/kernel/ 2>/dev/null | head -n 1)
case "$(uname -r) $kernel" in
    "5.10.186+ 2.0.7"|"5.10.186+ 2.0.8") ;;
    *) say "kernel $(uname -r) (package ${kernel:-unknown}) not supported; not loading"; exit 0 ;;
esac
cd "$DIR" || exit 0
if ! sha256sum -c -s SHA256SUMS; then
    say "module files don't match SHA256SUMS; not loading"
    exit 0
fi
for m in $(cat LOAD_ORDER); do
    name=$(basename "$m" .ko)
    grep -q "^$name " /proc/modules && continue
    insmod "./$m" 2>>"$LOG" || { say "insmod $m failed"; exit 0; }
done
say "modules loaded"

# A cable pulled out leaves the adapter's routes in place: ignore them, so
# traffic falls back to Wi-Fi at once.
echo 1 > /proc/sys/net/ipv4/conf/all/ignore_routes_with_linkdown 2>/dev/null

(
    while true; do
        wired=
        for path in /sys/class/net/eth* /sys/class/net/enx* /sys/class/net/usb*; do
            [ -e "$path" ] || continue
            iface=${path##*/}
            if [ "$(cat "$path/operstate" 2>/dev/null)" = down ]; then
                ip link set "$iface" up 2>/dev/null
            fi
            if [ ! -f "/tmp/udhcpc-$iface.pid" ] ||
                ! kill -0 "$(cat "/tmp/udhcpc-$iface.pid")" 2>/dev/null; then
                say "$iface: starting DHCP"
                udhcpc -i "$iface" -b -p "/tmp/udhcpc-$iface.pid" >/dev/null 2>&1
            fi
            [ "$(cat "$path/carrier" 2>/dev/null)" = 1 ] &&
                ip -4 addr show "$iface" | grep -q 'inet ' && wired=$iface
        done
        # Wi-Fi's routes get metric 0 again on every lease renewal: move them
        # behind the wired ones while an adapter has an address
        if [ -n "$wired" ]; then
            ip -4 route show dev wlan0 2>/dev/null | grep -v ' metric ' | while IFS= read -r route; do
                ip route add $route dev wlan0 metric 100 2>/dev/null
                ip route del $route dev wlan0 2>/dev/null
            done
        fi
        sleep 10
    done
) &
