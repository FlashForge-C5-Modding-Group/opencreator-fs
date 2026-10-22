#!/bin/sh
# OpenCreator Updater: merges opencreator-fs config updates into the live
# config and keeps OpenCreator's own files current, watching the
# opencreator-fs checkout Moonraker's update manager pulls. The work is in
# ../opencreator_updater.py (shared with tunnel SBCs); see
# config-docs/UPDATER.md. Logs to /tmp/opencreator-updater.log.
LOG=/tmp/opencreator-updater.log
HERE=$(cd "$(dirname "$0")/.." && pwd)
export PATH=$PATH:/opt/bin
# FlashForge's startup passes on its LD_LIBRARY_PATH, whose old libraries
# break Entware's git and curl; nothing here needs it.
unset LD_LIBRARY_PATH

for py in /usr/data/python-hf/bin/python3 /usr/data/opencreator/klipper/klippy-env/bin/python /opt/bin/python3; do
    if [ -x "$py" ]; then
        exec "$py" "$HERE/opencreator_updater.py" soc
    fi
done
echo "$(date '+%Y-%m-%d %H:%M:%S') no Python found; updater not running" >>"$LOG"
