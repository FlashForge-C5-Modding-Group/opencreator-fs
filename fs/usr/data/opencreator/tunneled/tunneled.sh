#!/bin/sh

# Based on original C5 Tunneled,

export LD_LIBRARY_PATH=/usr/prog/Python-3.8.2/lib:/usr/prog/openssl-1.0.2d/lib:/usr/prog/libffi-3.4.4/lib:$LD_LIBRARY_PATH



while true; do
    /usr/prog/Python-3.8.2/bin/python3 /usr/prog/c5-tunnel/c5_bridge.py
    sleep 3
done