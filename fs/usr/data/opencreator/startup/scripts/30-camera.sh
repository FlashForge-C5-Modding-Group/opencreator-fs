#!/bin/sh
LAUNCHER_LOG="/tmp/opencreator.log"
log_launcher() {
    echo "$1" >> "$LAUNCHER_LOG"
}

log_launcher "Launching Webcam..."

sh /usr/prog/mjpg-streamer/start_webcam.sh