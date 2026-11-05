#!/bin/sh
API=http://127.0.0.1:7125/server/database/item
MACROS=/usr/data/opencreator/fluidd/macros.json
export PATH=$PATH:/opt/bin
# FlashForge's startup passes on its LD_LIBRARY_PATH, whose old libcurl
# breaks curl (undefined symbol curl_mime_free); nothing here needs it.
unset LD_LIBRARY_PATH

i=0
until curl -fs http://127.0.0.1:7125/server/info >/dev/null 2>&1; do
    i=$((i + 1))
    [ $i -ge 120 ] && exit 0
    sleep 5
done

post() {
    curl -fs -X POST -H 'Content-Type: application/json' -d @- "$API" >/dev/null
}

# Seeded once; after that the key exists and the user's edits are kept
if [ -f "$MACROS" ] && ! curl -fs "$API?namespace=fluidd&key=macros" >/dev/null 2>&1; then
    { printf '{"namespace":"fluidd","key":"macros","value":'; cat "$MACROS"; printf '}'; } | post
fi

# Hides timelapse's per-frame SET_GCODE_VARIABLE from the console
if ! curl -fs "$API?namespace=fluidd&key=console.consoleFilters" >/dev/null 2>&1; then
    printf '%s' '{"namespace":"fluidd","key":"console.consoleFilters","value":[{"id":"opencreator-timelapse","enabled":true,"name":"Timelapse frames","type":"contains","value":"TIMELAPSE_TAKE_FRAME"}]}' | post
fi
