#!/bin/sh
# USB serial and USB Ethernet. On FlashForge's kernels, loads the modules in
# ../usb-modules; on every kernel, gives any USB Ethernet adapter an address by
# DHCP and prefers it over Wi-Fi while it's connected. Runs on tunneled printers
# too (tunneled.sh). See config-docs/CREATOR5_USB_ETHERNET.md.
#
# Serial: loaded on kernel packages 2.0.0-2.0.6 and 2.0.8; 2.0.7 builds
# usb-serial in. Ethernet: no FlashForge kernel has it, so it's loaded on all
# of them. Custom kernels (OpenCreator's c5-kernel) build both in and load no
# modules.
DIR=/usr/data/opencreator/startup/usb-modules
LOG=/usr/data/logs/usb.log
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }

kernel=$(ls /usr/prog/PROGRAM/kernel/ 2>/dev/null | head -n 1)
if [ -e /proc/config.gz ]; then
    # FlashForge's kernels have no IKCONFIG; c5-kernel has /proc/config.gz
    say "custom kernel $(uname -r): drivers built in, no modules loaded"
elif ! (cd "$DIR" && sha256sum -c -s SHA256SUMS); then
    say "module files don't match SHA256SUMS; not loading"
else
    case "$kernel" in
        2.0.[0-6]|2.0.8) serial=1 ;;
        *) serial= ;;
    esac
    for m in $(cat "$DIR/LOAD_ORDER"); do
        name=$(basename "$m" .ko)
        case "$name" in
            usbserial|usb-serial-simple|ch341|cdc-acm) [ -n "$serial" ] || continue ;;
        esac
        # lsmod lists cdc-acm.ko as cdc_acm
        grep -q "^$(echo "$name" | tr - _) " /proc/modules && continue
        # insmod refuses modules built for another kernel; that's logged here
        insmod "$DIR/$m" 2>>"$LOG" || say "insmod $m failed"
    done
    if [ -n "$serial" ]; then serial="loaded"; else serial="skipped"; fi
    say "kernel $(uname -r) (package ${kernel:-unknown}): modules loaded, serial $serial"
fi

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
