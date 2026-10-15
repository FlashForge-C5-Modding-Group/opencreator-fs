#!/bin/sh
API=http://127.0.0.1:7125/server/database/item
MACROS=/usr/data/opencreator/fluidd/macros.json
export PATH=$PATH:/opt/bin
[ -f "$MACROS" ] || exit 0

i=0
until curl -fs http://127.0.0.1:7125/server/info >/dev/null 2>&1; do
    i=$((i + 1))
    [ $i -ge 120 ] && exit 0
    sleep 5
done

curl -fs "$API?namespace=fluidd&key=macros" >/dev/null 2>&1 && exit 0
{ printf '{"namespace":"fluidd","key":"macros","value":'; cat "$MACROS"; printf '}'; } |
    curl -fs -X POST -H 'Content-Type: application/json' -d @- "$API" >/dev/null
