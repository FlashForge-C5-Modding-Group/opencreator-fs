#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

MJPG_DIR=/usr/prog/mjpg-streamer
USTREAMER=/usr/data/opencreator/camera/ustreamer
CAMERA_CONF=/usr/data/opencreator/klipper/config/camera.conf
DEVICE=/dev/video0
LOGS=/usr/data/logs
FAILS_ALLOWED=3     # ustreamer stopping this many times running goes back to mjpg_streamer
SHORT_RUN_S=30      # a run shorter than this counts as stopping
# ustreamer is downloaded the first time it's chosen, and again when this changes.
# Built by c5/build.sh on the creator5 branch of FlashForge-C5-Modding-Group/ustreamer.
USTREAMER_URL=https://github.com/FlashForge-C5-Modding-Group/ustreamer/releases/download/0.0.1/ustreamer
USTREAMER_SHA256=2b9e4a1313e83371a8a209c2781d0a665a3be7789514c7b6596da9da758d1710
FETCH_TRIES=10      # the network can still be coming up at boot
FETCH_WAIT_S=6

log_launcher "Launching Webcam..."

export LD_LIBRARY_PATH=$MJPG_DIR

# The streamer is chosen in camera.conf, in the config folder: mjpg_streamer, or
# ustreamer (experimental). Read at boot.
if [ ! -f "$CAMERA_CONF" ] && [ -d "$(dirname "$CAMERA_CONF")" ]; then
    printf '%s\n' "# Camera streamer, read at boot: mjpg_streamer, or ustreamer (experimental)" \
        "streamer: mjpg_streamer" > "$CAMERA_CONF"
fi
STREAMER=$(sed -n 's/^[[:space:]]*streamer[[:space:]]*[:=][[:space:]]*\([A-Za-z_]*\).*/\1/p' \
    "$CAMERA_CONF" 2>/dev/null | head -n 1)

# id=value: white balance auto off, white balance 4800K (auto comes out
# blue, 5500K and up orange), saturation 100, contrast 33, hue -20
# Below Klippy (see config-docs/CREATOR5_CPU_PRIORITY.md)
NICE=
nice -n 10 true 2>/dev/null && NICE="nice -n 10"

CONTROLS="9963788=0 9963802=4800 9963778=100 9963777=33 9963779=-20"

# Sent once mjpg_streamer answers, and again until the camera reports every
# value (a camera that is still starting drops them).
apply_controls() {
  i=0
  while [ "$i" -lt 60 ]; do
    sleep 2
    i=$((i+1))
    json=$(wget -q -O - "http://127.0.0.1:8080/input.json" 2>/dev/null | tr -d ' \n') || continue
    [ -n "$json" ] || continue
    missing=0
    for c in $CONTROLS; do
      echo "$json" | grep -q "\"id\":\"${c%%=*}\"[^}]*\"value\":\"${c#*=}\"" && continue
      missing=1
      wget -q -O /dev/null "http://127.0.0.1:8080/?action=command&dest=0&plugin=0&group=1&id=${c%%=*}&value=${c#*=}"
    done
    [ "$missing" = 0 ] && return 0
  done
  log_launcher "Webcam: could not apply the camera settings"
}

# The same camera settings, given at start. The camera's own MJPEG goes out as is
# (HW), and Allow-Origin keeps Fluidd's adaptive mode working across the port.
run_ustreamer() {
  $NICE "$USTREAMER" --device=$DEVICE --format=MJPEG --encoder=HW \
    --resolution=1280x720 --desired-fps=30 --host=0.0.0.0 --port=8080 \
    --allow-origin='*' --drop-same-frames=30 \
    --white-balance=4800 --saturation=100 --contrast=33 --hue=-20 \
    >$LOGS/ustreamer.log 2>&1
}

sha256_of() {
  sha256sum "$1" 2>/dev/null | cut -c1-64
}

# 0 once $USTREAMER is the pinned build. A copy that doesn't match is replaced;
# if the download fails, an older copy is still used.
fetch_ustreamer() {
  [ "$(sha256_of "$USTREAMER")" = "$USTREAMER_SHA256" ] && return 0
  mkdir -p "$(dirname "$USTREAMER")"
  # the stock curl has no CA certificates, so it can't reach GitHub: Entware's can
  CURL=curl
  [ -x /opt/bin/curl ] && CURL=/opt/bin/curl
  n=0
  while [ "$n" -lt "$FETCH_TRIES" ]; do
    n=$((n+1))
    rm -f "$USTREAMER.part"
    if $CURL -fsSL -m 120 -o "$USTREAMER.part" "$USTREAMER_URL" 2>/dev/null; then
      if [ "$(sha256_of "$USTREAMER.part")" = "$USTREAMER_SHA256" ]; then
        chmod 755 "$USTREAMER.part" && mv -f "$USTREAMER.part" "$USTREAMER"
        log_launcher "Webcam: downloaded ustreamer"
        return 0
      fi
      log_launcher "Webcam: the ustreamer download didn't match its checksum"
      break
    fi
    sleep "$FETCH_WAIT_S"
  done
  rm -f "$USTREAMER.part"
  [ -f "$USTREAMER" ] && { log_launcher "Webcam: couldn't update ustreamer, using the copy already here"; return 0; }
  return 1
}

run_mjpg_streamer() {
  apply_controls &
  $NICE ./mjpg_streamer \
    -i "input_uvc.so -d $DEVICE -r 1280x720 -f 30" \
    -o "output_http.so -p 8080 -w www" \
    >$LOGS/mjpg.log 2>&1
}

(
  cd $MJPG_DIR || exit 1
  # wait up to 30s for the camera
  i=0
  while [ ! -e $DEVICE ] && [ "$i" -lt 30 ]; do sleep 1; i=$((i+1)); done
  mkdir -p $LOGS

  use_ustreamer=0
  if [ "$STREAMER" = ustreamer ]; then
    if fetch_ustreamer; then
      [ -x "$USTREAMER" ] || chmod 755 "$USTREAMER"
      use_ustreamer=1
      log_launcher "Webcam: using ustreamer (experimental)"
    else
      log_launcher "Webcam: ustreamer is selected but couldn't be downloaded, using mjpg_streamer"
    fi
  fi

  # relaunch if the streamer ever exits
  fails=0
  while true; do
    if [ "$use_ustreamer" = 1 ]; then
      started=$(date +%s)
      run_ustreamer
      if [ $(( $(date +%s) - started )) -lt $SHORT_RUN_S ]; then fails=$((fails+1)); else fails=0; fi
      if [ "$fails" -ge $FAILS_ALLOWED ]; then
        use_ustreamer=0
        log_launcher "Webcam: ustreamer keeps stopping (see $LOGS/ustreamer.log), using mjpg_streamer"
      fi
    else
      run_mjpg_streamer
    fi
    sleep 3
  done
) &
