#!/bin/sh
# OpenCreator Updater (SoC/LoopScript v2 edition).
#
# Merges the fs/usr/data/config/*.cfg template from opencreator-fs into the
# live /usr/data/opencreator/klipper/config, keeping the user's own edits
# (diff of the template since the last run, patched onto the live file).
#
# Installer installs keep a git clone of opencreator-fs in
# /usr/data/opencreator/opencreator-fs that Moonraker's update manager
# updates ([update_manager opencreator]). This script merges from it at boot
# and then keeps watching it: after an update, the configs are merged and
# Klipper restarted (once nothing is printing). Without the clone it falls
# back to downloading the template once per boot.
#
# The first run has no base snapshot yet: it seeds the base and leaves live
# files untouched.
set -u

LOG=/tmp/opencreator-updater.log
CONFIG_DIR=/usr/data/opencreator/klipper/config
BASE_DIR="$CONFIG_DIR/.opencreator-updater/base"
APPLIED="$CONFIG_DIR/.opencreator-updater/applied-commit"
CLONE=/usr/data/opencreator/opencreator-fs
WORK=/tmp/opencreator-updater.work
KLIPPER_DIR=/usr/data/opencreator/klipper/klipper
KLIPPER_HASH_MARKER=/usr/data/opencreator/.opencreator-updater-klipper-tar-sha256
FS_URL=https://github.com/FlashForge-C5-Modding-Group/opencreator-fs/archive/refs/heads/main.tar.gz
KLIPPER_URL=https://github.com/FlashForge-C5-Modding-Group/kalico/archive/refs/heads/something.tar.gz
MOONRAKER_API=http://127.0.0.1:7125
export PATH=$PATH:/opt/bin

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }

# merge_configs TEMPLATE_DIR: sets CHANGED and CONFLICTS.
merge_configs() {
    TEMPLATE_DIR=$1
    mkdir -p "$WORK" "$BASE_DIR"
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

        # CRLF in any of the three would make every context line mismatch.
        tr -d '\r' <"$base" >"$WORK/$name.base"
        tr -d '\r' <"$template" >"$WORK/$name.template"
        tr -d '\r' <"$live" >"$WORK/$name.live"
        diff -u "$WORK/$name.base" "$WORK/$name.template" >"$WORK/$name.patch" 2>/dev/null
        # Default fuzz: exact context breaks when the user edited a nearby line.
        if patch --no-backup-if-mismatch -o "$WORK/$name.merged" "$WORK/$name.live" \
            <"$WORK/$name.patch" >"$WORK/$name.patchlog" 2>&1; then
            mv "$WORK/$name.merged" "$live"
            cp "$template" "$base"
            log "$name: merged"
            CHANGED=1
        else
            CONFLICTS="$CONFLICTS $name"
            log "$name: CONFLICT -- template changed a line the live config" \
                "also changed; leaving both files as-is."
        fi
    done
}

printing() {
    curl -fsS --max-time 5 "$MOONRAKER_API/printer/objects/query?print_stats=state" 2>/dev/null |
        grep -Eq '"state": *"(printing|paused)"'
}

restart_klipper() {
    if [ -n "$CONFLICTS" ]; then
        log "CONFLICTS in:$CONFLICTS -- resolve by hand, then restart Klipper"
        return
    fi
    [ "$CHANGED" = 1 ] || { log "nothing changed"; return; }
    while printing; do sleep 60; done
    if curl -fsS --max-time 10 -X POST "$MOONRAKER_API/printer/restart" >/dev/null 2>&1; then
        log "klipper restart requested via Moonraker API"
    else
        log "klipper restart request failed; restart manually"
    fi
}

apply_clone() {
    head=$(git -C "$CLONE" rev-parse HEAD 2>/dev/null) || return
    [ "$head" != "$(cat "$APPLIED" 2>/dev/null)" ] || return
    log "applying opencreator-fs $head"
    CHANGED=0
    CONFLICTS=""
    rm -rf "$WORK"
    merge_configs "$CLONE/fs/usr/data/config"
    rm -rf "$WORK"
    mkdir -p "$(dirname "$APPLIED")"
    echo "$head" >"$APPLIED"
    restart_klipper
}

if [ -d "$CLONE/.git" ]; then
    # Wait for Moonraker so a restart request can reach it.
    i=0
    until curl -fs --max-time 5 "$MOONRAKER_API/server/info" >/dev/null 2>&1; do
        i=$((i + 1))
        [ "$i" -ge 120 ] && break
        sleep 5
    done
    while true; do
        apply_clone
        sleep 60
    done
fi

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
merge_configs "$TEMPLATE_DIR"

log "refreshing klipper source"
if [ -d "$KLIPPER_DIR/.git" ]; then
    log "klipper: git checkout, updated through Moonraker's update manager"
elif curl -fsSL --max-time 120 -o "$WORK/klipper.tar.gz" "$KLIPPER_URL"; then
    new_hash=$(sha256sum "$WORK/klipper.tar.gz" | cut -d' ' -f1)
    old_hash=$(cat "$KLIPPER_HASH_MARKER" 2>/dev/null || echo "")
    if [ "$new_hash" != "$old_hash" ]; then
        tar -xzf "$WORK/klipper.tar.gz" -C "$WORK"
        KSRC=$(find "$WORK" -maxdepth 1 -type d -name 'kalico-*')
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

restart_klipper
rm -rf "$WORK"
