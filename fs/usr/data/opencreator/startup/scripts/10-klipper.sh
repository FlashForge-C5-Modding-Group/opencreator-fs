#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
OC=/usr/data/opencreator/klipper
KPY=$OC/klippy-env/bin/python
# python-hf/cc/bin/gcc rebuilds c_helper.so (hard-float) after Kalico updates.
export PATH=/usr/data/python-hf/cc/bin:$PATH:/opt/bin

log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

# AFC stops with an error while its variables file is missing or empty; it
# fills the file in itself once it has state to save.
AFC_VARS=$OC/config/AFC/AFC.var.unit
if [ ! -s "$AFC_VARS" ]; then
    mkdir -p "$OC/config/AFC"
    echo '{}' > "$AFC_VARS"
fi

PLUGINS=/usr/data/opencreator/plugin-manager/oc-plugin
[ -d /opt/bin ] && [ -f "$PLUGINS" ] && ln -sf "$PLUGINS" /opt/bin/oc-plugin

while true; do
    if [ -x "$KPY" ]; then
        # Plugin modules and configs, redone before every start (Fluidd updates plugins with git pull)
        [ -f "$PLUGINS" ] && sh "$PLUGINS" sync --only klipper >> "$LAUNCHER_LOG" 2>&1
        log_launcher "Klippy is starting..."

        "$KPY" "$OC/klipper/klippy/klippy.py" "$OC/config/printer.cfg" -l "$OC/logs/printer.log" -a /tmp/uds

        log_launcher "Klippy exited; see $OC/logs/printer.log. Restarting in 3 s."
        log_launcher "ERR CODE 0 - Klippy"
    fi
    sleep 3
done
