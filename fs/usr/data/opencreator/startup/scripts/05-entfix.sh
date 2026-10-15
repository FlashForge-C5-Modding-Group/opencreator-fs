#!/bin/sh
[ -d /usr/data/bin/opt ] || exit 0
sh /usr/data/opencreator/startup/scripts/01-fixnan.sh || exit 1
grep -q ' /opt ' /proc/mounts || mount --bind /usr/data/bin/opt /opt
[ -x /opt/etc/init.d/rc.unslung ] && /opt/etc/init.d/rc.unslung start
