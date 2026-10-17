#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

log_launcher "Launching Webcam..."

export LD_LIBRARY_PATH=/usr/prog/mjpg-streamer

# id=value: white balance auto on, saturation 100, contrast 33, hue -20
CONTROLS="9963788=1 9963778=100 9963777=33 9963779=-20"

apply_controls() {
  sleep 5
  for c in $CONTROLS; do
    wget -q -O /dev/null "http://127.0.0.1:8080/?action=command&dest=0&plugin=0&group=1&id=${c%%=*}&value=${c#*=}"
  done
}

(
  cd /usr/prog/mjpg-streamer || exit 1
  # wait up to 30s for the camera
  i=0
  while [ ! -e /dev/video0 ] && [ "$i" -lt 30 ]; do sleep 1; i=$((i+1)); done
  mkdir -p /usr/data/logs

  # relaunch if mjpg_streamer ever exits
  while true; do
    apply_controls &
    ./mjpg_streamer \
      -i "input_uvc.so -d /dev/video0 -r 1280x720 -f 30" \
      -o "output_http.so -p 8080 -w www" \
      >/usr/data/logs/mjpg.log 2>&1
    sleep 3
  done
) &
