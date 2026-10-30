#!/bin/sh
# A new address for the network wpa_supplicant just joined
pids=$(ps w | awk '/udhcpc -i wlan0/ && !/awk/ {print $1}')
[ -z "$pids" ] || kill $pids
exec udhcpc -i wlan0 -b
