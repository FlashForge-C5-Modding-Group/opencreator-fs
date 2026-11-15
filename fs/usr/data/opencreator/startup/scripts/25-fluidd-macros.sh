#!/bin/sh
API=http://127.0.0.1:7125/server/database/item
MACROS=/usr/data/opencreator/fluidd/macros.json
CONFIG=/usr/data/opencreator/klipper/config
MPY=/usr/prog/moonraker/moonraker-env/bin/python
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

# The installer turns the VDS dryer on with printer.accessory.dryer.cfg; give its
# macros their own "VDS Macros" category. Macros the user already placed stay put.
if [ -f "$CONFIG/printer.accessory.dryer.cfg" ] && [ -f "$CONFIG/printer.dryer.cfg" ] && [ -x "$MPY" ]; then
    "$MPY" - "$API" "$CONFIG/printer.dryer.cfg" <<'EOF'
import json, re, sys, uuid, urllib.request
api, cfg = sys.argv[1], sys.argv[2]
names = re.findall(r"^\[gcode_macro (C5_DRYER_\w+)\]", open(cfg).read(), re.M)
try:
    with urllib.request.urlopen(api + "?namespace=fluidd&key=macros", timeout=10) as r:
        val = json.load(r)["result"]["value"]
except Exception:
    val = {}
cats = val.setdefault("categories", [])
stored = val.setdefault("stored", [])
expanded = val.setdefault("expanded", [])
cat = next((c for c in cats if c.get("name") == "VDS Macros"), None)
changed = False
if cat is None:
    cat = {"id": str(uuid.uuid4()), "name": "VDS Macros"}
    cats.append(cat)
    expanded.append(len(cats))
    changed = True
have = {m.get("name", "").upper() for m in stored}
for n in names:
    if n not in have:
        stored.append({"alias": "", "visible": True, "disabledWhilePrinting": True,
                       "color": "", "categoryId": cat["id"], "name": n})
        changed = True
if changed:
    body = json.dumps({"namespace": "fluidd", "key": "macros", "value": val}).encode()
    req = urllib.request.Request(api, body, {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()
EOF
fi

# Hides timelapse's per-frame SET_GCODE_VARIABLE from the console
if ! curl -fs "$API?namespace=fluidd&key=console.consoleFilters" >/dev/null 2>&1; then
    printf '%s' '{"namespace":"fluidd","key":"console.consoleFilters","value":[{"id":"opencreator-timelapse","enabled":true,"name":"Timelapse frames","type":"contains","value":"TIMELAPSE_TAKE_FRAME"}]}' | post
fi
