#!/bin/sh
# Login banner and bash prompt (see config-docs/CREATOR5_LOGIN.md)
LAUNCHER_LOG="/tmp/opencreator.log"
SRC=/usr/data/opencreator/startup/login/profile.sh
DEST=/etc/profile.d/opencreator.sh

[ -d /etc/profile.d ] && [ -f "$SRC" ] || exit 0
[ "$(readlink "$DEST" 2>/dev/null)" = "$SRC" ] && exit 0
ln -sf "$SRC" "$DEST" && echo "Login banner installed" >> "$LAUNCHER_LOG"
