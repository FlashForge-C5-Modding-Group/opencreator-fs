#!/bin/sh
# OpenCreator Updater (SoC/LoopScript v2 edition).
#
# On every boot: merges the latest fs/usr/data/config/*.cfg template from
# opencreator-fs into the live /usr/data/config, preserving values the
# user has customized (speeds, spoolman, toggle defaults, etc), then
# refreshes the Klipper source baked into /usr/prog/klipper. Dispatched
# once per boot by startup.sh like every other script in this directory
# -- there is no systemd here to trigger it from Moonraker's update
# manager the way the Pi-tunnel version works (see
# opencreator-tunnel/pi/opencreator-updater), so this runs unconditionally
# at boot instead of on demand.
#
# This image's buildroot has no git -- only Entware's /opt/bin/git, which
# by project convention is off-limits (use what actually ships on this
# image, not /opt; see firmwareExe in the tunnel setup for the same rule
# applied to Python). So merging uses plain diff+patch instead of git
# merge-file: the template's changes since the last run are turned into a
# patch (diff -u base latest) and applied onto the live file. If that
# patch applies cleanly, the user's independent edits elsewhere in the
# file survive (patch only touches the context around lines that
# actually changed upstream). If it does not apply cleanly, that means
# the template changed a line the user also changed -- left alone and
# logged as a conflict rather than guessed at.
#
# First run has no base snapshot yet, so there is nothing to diff the
# template against: it seeds the base and leaves live files untouched.
# Real auto-merging starts on the run after that one, same as the
# Pi-tunnel version and for the same reason -- there is no reliable way
# to know what template version a pre-existing live file started from.
set -u

LOG=/tmp/opencreator-updater.log
CONFIG_DIR=/usr/data/config
BASE_DIR="$CONFIG_DIR/.opencreator-updater/base"
WORK=/tmp/opencreator-updater.work
KLIPPER_DIR=/usr/prog/klipper
KLIPPER_HASH_MARKER=/usr/data/opencreator/.opencreator-updater-klipper-tar-sha256
FS_URL=https://github.com/FlashForge-C5-Modding-Group/opencreator-fs/archive/refs/heads/main.tar.gz
KLIPPER_URL=https://github.com/FlashForge-C5-Modding-Group/klipper-c5/archive/refs/heads/master.tar.gz
MOONRAKER_API=http://127.0.0.1:7125

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }

rm -rf "$WORK"
mkdir -p "$WORK" "$BASE_DIR"

log "waiting for network"
tries=0
until curl -fsS --max-time 5 -o /dev/null https://github.com; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
        log "no network after 60s, giving up this boot"
        exit 0
    fi
    sleep 2
done

log "downloading opencreator-fs template"
if ! curl -fsSL --max-time 60 -o "$WORK/opencreator-fs.tar.gz" "$FS_URL"; then
    log "download failed, giving up this boot"
    rm -rf "$WORK"
    exit 0
fi
tar -xzf "$WORK/opencreator-fs.tar.gz" -C "$WORK"
TEMPLATE_DIR=$(find "$WORK" -maxdepth 1 -type d -name 'opencreator-fs-*')/fs/usr/data/config
if [ ! -d "$TEMPLATE_DIR" ]; then
    log "template dir missing after extract, giving up this boot"
    rm -rf "$WORK"
    exit 0
fi

CHANGED=0
CONFLICTS=""
for template in "$TEMPLATE_DIR"/*.cfg; do
    name=$(basename "$template")
    live="$CONFIG_DIR/$name"
    base="$BASE_DIR/$name"

    if [ ! -f "$live" ]; then
        cp "$template" "$live"
        cp "$template" "$base"
        log "$name: new"
        CHANGED=1
        continue
    fi
    if [ ! -f "$base" ]; then
        cp "$template" "$base"
        log "$name: bootstrap (tracking only, live file untouched)"
        continue
    fi
    if cmp -s "$base" "$template"; then
        log "$name: unchanged"
        continue
    fi

    # Normalize CRLF before diffing/patching: a live file that picked up
    # CRLF endings at some point (this repo is maintained on Windows, so
    # it's not guaranteed every path that lands a config on the printer
    # keeps it LF-only) would otherwise fail every context-line match
    # against an LF-only base/template, since patch compares lines as
    # exact strings including the trailing \r. That just means a wasted
    # conflict report here (patch's own all-or-nothing hunk application
    # means a mismatch never reaches `mv`, so the live file was never at
    # risk of corruption the way the Pi-side git-merge-file tool was),
    # but it is still worth avoiding -- normalize all three to LF for
    # the comparison, and write the merged result back as LF too.
    tr -d '\r' <"$base" >"$WORK/$name.base"
    tr -d '\r' <"$template" >"$WORK/$name.template"
    tr -d '\r' <"$live" >"$WORK/$name.live"
    diff -u "$WORK/$name.base" "$WORK/$name.template" >"$WORK/$name.patch" 2>/dev/null
    # Default fuzz (not 0): tested empirically -- a strict exact-context
    # match breaks the common case where the template's hunk context
    # happens to border a line the user independently customized nearby
    # (not the changed line itself), which is routine in these configs.
    if patch --no-backup-if-mismatch -o "$WORK/$name.merged" "$WORK/$name.live" \
        <"$WORK/$name.patch" >"$WORK/$name.patchlog" 2>&1; then
        mv "$WORK/$name.merged" "$live"
        cp "$template" "$base"
        log "$name: merged"
        CHANGED=1
    else
        CONFLICTS="$CONFLICTS $name"
        log "$name: CONFLICT -- template changed a line the live config" \
            "also changed; leaving both files as-is." \
            "See $WORK/$name.patchlog before it's cleaned up, or rerun" \
            "to regenerate it."
    fi
done

log "refreshing klipper source"
if curl -fsSL --max-time 120 -o "$WORK/klipper.tar.gz" "$KLIPPER_URL"; then
    new_hash=$(sha256sum "$WORK/klipper.tar.gz" | cut -d' ' -f1)
    old_hash=$(cat "$KLIPPER_HASH_MARKER" 2>/dev/null || echo "")
    if [ "$new_hash" != "$old_hash" ]; then
        tar -xzf "$WORK/klipper.tar.gz" -C "$WORK"
        KSRC=$(find "$WORK" -maxdepth 1 -type d -name 'klipper-c5-*')
        if [ -n "$KSRC" ] && [ -d "$KSRC/klippy" ]; then
            mkdir -p "$KLIPPER_DIR/klippy"
            cp -R "$KSRC/klippy/." "$KLIPPER_DIR/klippy/"
            echo "$new_hash" >"$KLIPPER_HASH_MARKER"
            log "klipper: updated ($old_hash -> $new_hash)"
            CHANGED=1
        else
            log "klipper: extracted tree missing klippy/, leaving current install alone"
        fi
    else
        log "klipper: already up to date"
    fi
else
    log "klipper: download failed, leaving current install alone"
fi

if [ -n "$CONFLICTS" ]; then
    log "CONFLICTS in:$CONFLICTS -- resolve by hand, then restart Klipper"
elif [ "$CHANGED" = 1 ]; then
    if curl -fsS --max-time 10 -X POST "$MOONRAKER_API/printer/restart" >/dev/null 2>&1; then
        log "klipper restart requested via Moonraker API"
    else
        log "klipper restart request failed; restart manually"
    fi
else
    log "nothing changed"
fi

rm -rf "$WORK"
