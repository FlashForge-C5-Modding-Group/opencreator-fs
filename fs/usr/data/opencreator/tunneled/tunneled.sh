#!/bin/sh

# Based on original C5 Tunneled,

SCRIPTS=/usr/data/opencreator/startup/scripts
export LD_LIBRARY_PATH=/usr/prog/Python-3.8.2/lib:/usr/prog/openssl-1.0.2d/lib:/usr/prog/libffi-3.4.4/lib:$LD_LIBRARY_PATH
export PATH=$PATH:/opt/bin
chmod 755 /usr/data/opencreator/tunneled/oc-tunneled 2>/dev/null
[ -d /opt/bin ] && ln -sf /usr/data/opencreator/tunneled/oc-tunneled /opt/bin/oc-tunneled
[ -d /opt/bin ] && ln -sf /usr/data/opencreator/startup/commands/oc-switchscreen /opt/bin/oc-switchscreen

# MCU firmware the installer left for this power-on, before the tunnel wakes the boards
[ ! -f /usr/data/opencreator/mcu-flash-pending/flash.sh ] ||
    sh /usr/data/opencreator/mcu-flash-pending/flash.sh > /tmp/mcu-flash-pending.log 2>&1

sh "$SCRIPTS/05-entfix.sh"
sh "$SCRIPTS/06-sftp.sh"
# No clock battery: set the clock from the network (it keeps doing so in the background), so
# git's HTTPS and plugins see the right date. Not with FlashForge's libraries.
(unset LD_LIBRARY_PATH; sh "$SCRIPTS/02-fixtime.sh")
sh "$SCRIPTS/30-camera.sh" &
sh "$SCRIPTS/40-grumpyscreen.sh" &
sh "$SCRIPTS/41-helixscreen.sh" &
# Plugins made for tunneled printers (their startup items only)
PLUGINS=/usr/data/opencreator/plugin-manager/oc-plugin
if [ -f "$PLUGINS" ]; then
    [ -d /opt/bin ] && ln -sf "$PLUGINS" /opt/bin/oc-plugin
    sh "$PLUGINS" boot > /tmp/oc-plugin-boot.log 2>&1 &
fi

while true; do
    /usr/prog/Python-3.8.2/bin/python3 /usr/prog/c5-tunnel-socat/c5_socat.py
    sleep 3
done
