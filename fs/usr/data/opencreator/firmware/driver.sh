#!/bin/sh
# Run by the stock rootfs's S11, before app_startup.sh: runRecovery.sh from a
# USB stick, and OpenCreator even when app_startup.sh is broken.

LOG=/tmp/early.log
exec >> "$LOG" 2>&1
echo "$(date '+%F %T') early boot hook"

FWEXE=/usr/prog/PROGRAM/software/firmwareExe
FF_UPDATE=0

# The same mount S21 does later; S21 then finds it mounted and leaves it alone.
grep -q ' /usr/data ' /proc/mounts || mount_mmc_ext4.sh userdata /usr/data/

usb_scan() {
	MNT=/tmp/recovery-usb
	n=0
	while [ ! -e /dev/sda ] && [ $n -lt 30 ]; do sleep 0.1; n=$((n + 1)); done
	[ -e /dev/sda ] || { echo "usb: no stick"; return; }
	sleep 1
	mkdir -p "$MNT"
	ran=0
	for dev in /dev/sda1 /dev/sda2 /dev/sda3 /dev/sda4 /dev/sda; do
		[ -e "$dev" ] || continue
		mount -o ro "$dev" "$MNT" 2>/dev/null || continue
		if ls "$MNT"/Creator5*.tgz >/dev/null 2>&1 || [ -f "$MNT/runFirmwareExe.sh" ]; then
			echo "usb: FlashForge update on $dev"
			FF_UPDATE=1
		fi
		if [ $ran = 0 ] && [ -f "$MNT/runRecovery.sh" ]; then
			ran=1
			mount -o remount,rw "$MNT"
			echo "usb: running runRecovery.sh from $dev"
			(
				cd "$MNT"
				export RECOVERY_DIR="$MNT"
				echo "=== $(date '+%F %T') runRecovery.sh"
				sh ./runRecovery.sh
				echo "=== exit $?"
			) 2>&1 | tee -a "$MNT/runRecovery.log"
			sync
		fi
		umount "$MNT"
	done
}

control_update_pending() {
	d=/usr/prog/PROGRAM/control
	v=$(cd "$d" 2>/dev/null && ls -d [0-9]* 2>/dev/null | sort -Vr | head -n 1)
	[ -n "$v" ] && [ -f "$d/$v/Update" ]
}

fwexe_running() {
	for c in /proc/[0-9]*/cmdline; do
		{ tr '\0' ' ' < "$c"; } 2>/dev/null | grep -q '[P]ROGRAM/software/firmwareExe' && return 0
	done
	return 1
}

oc_boot() {
	grep -q ' /usr/data ' /proc/mounts || { echo "oc: /usr/data not mounted"; return; }
	[ -f "$FWEXE" ] || { echo "oc: no firmwareExe, leaving boot to stock"; return; }
	[ "$(head -c 4 "$FWEXE" | tail -c 3)" = ELF ] && { echo "oc: stock firmwareExe, not starting OpenCreator"; return; }
	grep -q opencreator.boot "$FWEXE" || { echo "oc: firmwareExe has no boot lock, leaving it to app_startup.sh"; return; }
	[ $FF_UPDATE = 1 ] && { echo "oc: FlashForge update on USB, leaving it to app_startup.sh"; return; }
	control_update_pending && { echo "oc: control update pending, leaving it to app_startup.sh"; return; }

	# Start once app_startup.sh has bind-mounted /usr/prog/etc over /etc; do it
	# here if that hasn't happened in 60 s.
	n=0
	while ! grep -q ' /etc ' /proc/mounts && [ $n -lt 600 ]; do sleep 0.1; n=$((n + 1)); done
	if ! grep -q ' /etc ' /proc/mounts; then
		echo "oc: app_startup.sh didn't mount /etc, doing its setup"
		[ -d /usr/prog/etc ] && mount /usr/prog/etc /etc
	fi
	[ -d /tmp/opencreator.boot ] || fwexe_running && { echo "oc: already started"; return; }

	insmod /usr/prog/modules/soc_mcu.ko enable_jtag_debug=1 2>/dev/null
	insmod /usr/prog/modules/8821cu.ko power_on=PB07 2>/dev/null
	insmod /usr/prog/modules/gt9xx_touch.ko gtp_i2c_bus_num=0 gtp_x_coords_min=0 gtp_y_coords_min=0 \
		gtp_x_coords_max=800 gtp_y_coords_max=480 gtp_x_coords_flip=0 gtp_y_coords_flip=0 \
		gtp_x_y_coords_exchange=0 gtp_version=0x4 gtp_regulator_name=-1 gtp_power_on_gpio=-1 \
		gtp_reset_gpio=PC08 gtp_irq_gpio=PC07 gtp_max_touch_number=2 2>/dev/null
	for l in openssl-1.0.2d/lib curl-7.55.1/lib ffmpeg-402/lib x264/lib libffi-3.4.4/lib libsodium/lib \
	         opencv-4.2/lib mjpg-streamer nim/lib libzip-1.10.1/lib; do
		LD_LIBRARY_PATH=/usr/prog/$l${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
	done
	export LD_LIBRARY_PATH

	echo "oc: starting OpenCreator ($FWEXE)"
	"$FWEXE" &
}

usb_scan
oc_boot &
exit 0
