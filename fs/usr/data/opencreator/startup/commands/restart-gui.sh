#!/bin/sh
# 40-grumpyscreen.sh and 41-helixscreen.sh start the screen again
kill $(pidof grumpyscreen) $(pidof helix-watchdog) $(pidof helix-screen) 2>/dev/null
