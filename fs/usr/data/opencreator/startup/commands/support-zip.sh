#!/bin/sh
# support.zip in the config folder: recent logs, configs and system details
OC=/usr/data/opencreator/klipper
PYTHON=$OC/klippy-env/bin/python
WORK=$(mktemp -d /tmp/oc-support.XXXXXX) || exit 1
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/logs" "$WORK/config/AFC"

for log in "$OC"/logs/printer.log "$OC"/logs/moonraker.log "$OC"/logs/AFC.log /tmp/*.log; do
    [ -f "$log" ] && tail -c 2000000 "$log" > "$WORK/logs/${log##*/}"
done

for file in "$OC"/config/*.cfg "$OC"/config/moonraker.conf "$OC"/config/AFC/*.cfg; do
    [ -f "$file" ] || continue
    dest=$WORK/config/${file#"$OC"/config/}
    # notifier URLs and the like carry tokens
    sed -E 's/^([[:space:]]*[A-Za-z_]*(url|password|token|secret|key)[A-Za-z_]*[[:space:]]*[:=]).*/\1 <removed>/I' \
        "$file" > "$dest"
done

{
    date
    uname -a
    cat /usr/data/opencreator/version.txt /usr/data/opencreator/install.json
    git -C "$OC/klipper" log -1 --oneline
    git -C /usr/data/opencreator/opencreator-fs log -1 --oneline
    df -h /usr/data /tmp
    free
    ps w
} > "$WORK/system.txt" 2>&1

cd "$WORK" || exit 1
"$PYTHON" -c "import shutil; shutil.make_archive('$OC/config/support', 'zip', '.')"
