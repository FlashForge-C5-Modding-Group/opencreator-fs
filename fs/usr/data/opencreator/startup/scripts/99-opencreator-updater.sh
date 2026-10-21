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
# and then keeps watching it: after an update, LoopScript's own files are
# swapped in (used from the next boot), the configs are merged and Klipper
# restarted (once nothing is printing). Without the clone it falls back to
# downloading the config template once per boot.
#
# Without a base snapshot, recover only an exact historical template match.
# Unknown user-edited files need manual resolution, never a guessed baseline.
set -u

LOG=/tmp/opencreator-updater.log
CONFIG_DIR=/usr/data/opencreator/klipper/config
BASE_DIR="$CONFIG_DIR/.opencreator-updater/base"
APPLIED="$CONFIG_DIR/.opencreator-updater/applied-commit"
MERGE_VERSION=2
MERGE_VERSION_FILE="$CONFIG_DIR/.opencreator-updater/merge-version"
CLONE=/usr/data/opencreator/opencreator-fs
OCDIR=/usr/data/opencreator
LOOPSCRIPT_APPLIED=$OCDIR/.loopscript-commit
NGINX_CONF_D=/usr/data/nginx/conf.d
FIRMWARE_EXE=/usr/prog/PROGRAM/software/firmwareExe
WORK=/tmp/opencreator-updater.work
KLIPPER_DIR=/usr/data/opencreator/klipper/klipper
KLIPPER_HASH_MARKER=/usr/data/opencreator/.opencreator-updater-klipper-tar-sha256
FS_URL=https://github.com/FlashForge-C5-Modding-Group/opencreator-fs/archive/refs/heads/main.tar.gz
FS_GIT_URL=https://github.com/FlashForge-C5-Modding-Group/opencreator-fs.git
KLIPPER_URL=https://github.com/FlashForge-C5-Modding-Group/kalico/archive/refs/heads/something.tar.gz
MOONRAKER_API=http://127.0.0.1:7125
export PATH=$PATH:/opt/bin
# FlashForge's startup passes on its LD_LIBRARY_PATH, whose old libcurl
# breaks curl (undefined symbol curl_mime_free); nothing here needs it.
unset LD_LIBRARY_PATH

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }

# Normalize comparisons without discarding the live printer's calibration.
normalize_config() {
    tr -d '\r' <"$1" >"$2.crlf" &&
        sed '/^#\*# <-* SAVE_CONFIG -*>/,$d' "$2.crlf" >"$2"
}

# Historical lookup: 0 = exact match, 1 = complete no-match,
# 2 = unavailable history. Candidates stay in WORK until publication.
recover_baseline() {
    if [ "$HISTORY_STATE" = untried ]; then
        HISTORY_STATE=shallow
        HISTORY_REPO=$CLONE
        case $(git -C "$CLONE" rev-parse --is-shallow-repository 2>/dev/null) in
            false) HISTORY_STATE=ready ;;
            true) ;;
            *) HISTORY_REPO="" ;;
        esac
    fi
    # A shallow checkout may already contain the exact installed template.
    # A local miss is conclusive only when that checkout has complete history.
    if [ -n "$HISTORY_REPO" ]; then
        search_baseline "$1" "$2"
        history_status=$?
        [ "$history_status" = 0 ] && return 0
        [ "$history_status" = 2 ] && return 2
        [ "$HISTORY_STATE" = ready ] && return 1
    fi
    [ "$HISTORY_STATE" != failed ] || return 2
    HISTORY_STATE=failed
    if ! git clone -q --no-checkout "$FS_GIT_URL" "$WORK/history" >>"$LOG" 2>&1; then
        return 2
    fi
    HISTORY_REPO="$WORK/history"
    HISTORY_STATE=ready
    search_baseline "$1" "$2"
}

search_baseline() {
    history_path=fs/usr/data/config/$1
    git -C "$HISTORY_REPO" log --diff-filter=AM --format=%H HEAD -- "$history_path" \
        >"$WORK/history.commits" 2>>"$LOG" || return 2
    while IFS= read -r history_commit; do
        # Check extraction itself: a failed show must not match an empty live.
        git -C "$HISTORY_REPO" show "$history_commit:$history_path" \
            >"$WORK/history.raw" 2>>"$LOG" || return 2
        normalize_config "$WORK/history.raw" "$WORK/history.normalized" || return 2
        if cmp -s "$WORK/history.normalized" "$2"; then
            cp "$WORK/history.raw" "$WORK/$1.recovered" || return 2
            return 0
        fi
    done <"$WORK/history.commits"
    return 1
}

# Stage beside each destination so publication uses same-filesystem renames.
# If the base cannot be published, restore the live file before reporting failure.
publish_config() {
    [ ! -d "$3" ] && [ ! -d "$4" ] || return 1
    publish_had_live=0
    if [ -f "$3" ]; then
        cp "$3" "$3.opencreator-old" || return 1
        publish_had_live=1
    fi
    if ! cp "$1" "$3.opencreator-new" ||
        ! cp "$2" "$4.opencreator-new"; then
        rm -f "$3.opencreator-new" "$4.opencreator-new" "$3.opencreator-old"
        return 1
    fi
    if mv "$3.opencreator-new" "$3"; then
        if mv "$4.opencreator-new" "$4"; then
            rm -f "$3.opencreator-old"
            return 0
        fi
        if [ "$publish_had_live" = 1 ]; then
            if ! mv "$3.opencreator-old" "$3"; then
                log "$3: failed to restore live config; backup is $3.opencreator-old"
                rm -f "$4.opencreator-new"
                return 1
            fi
        else
            rm -f "$3"
        fi
    fi
    rm -f "$3.opencreator-new" "$4.opencreator-new" "$3.opencreator-old"
    return 1
}

# merge_configs TEMPLATE_DIR: sets CHANGED and CONFLICTS.
merge_configs() {
    TEMPLATE_DIR=$1
    HISTORY_STATE=untried
    HISTORY_REPO=""
    MIGRATION_PENDING=0
    [ "$MERGE_VERSION" = "$(cat "$MERGE_VERSION_FILE" 2>/dev/null)" ] ||
        MIGRATION_PENDING=1
    if ! mkdir -p "$WORK" "$BASE_DIR"; then
        CONFLICTS="$CONFLICTS config-state"
        return
    fi
    set -- "$TEMPLATE_DIR"/*.cfg
    if [ ! -f "$1" ]; then
        CONFLICTS="$CONFLICTS config-templates"
        log "CONFLICT -- config templates missing"
        return
    fi
    for template in "$@"; do
        name=$(basename "$template")
        live="$CONFIG_DIR/$name"
        base="$BASE_DIR/$name"

        if [ ! -f "$live" ]; then
            if publish_config "$template" "$template" "$live" "$base" \
                >>"$LOG" 2>&1; then
                log "$name: new"
                CHANGED=1
            else
                CONFLICTS="$CONFLICTS $name"
                log "$name: CONFLICT -- could not install config and baseline"
            fi
            continue
        fi
        # Historical recovery of poisoned bases is a one-time migration.
        # Afterwards an unchanged template must preserve deliberate user reverts.
        if [ "$MIGRATION_PENDING" = 0 ] &&
            [ -f "$base" ] && cmp -s "$base" "$template"; then
            log "$name: unchanged"
            continue
        fi
        # CRLF and SAVE_CONFIG are excluded only from comparisons/the patch.
        # The full live calibration is carried through the merge unchanged.
        if ! normalize_config "$template" "$WORK/$name.template" ||
            ! normalize_config "$live" "$WORK/$name.compare"; then
            CONFLICTS="$CONFLICTS $name"
            log "$name: CONFLICT -- could not normalize config"
            continue
        fi
        # The live file is already current: synchronize its baseline without
        # touching live bytes or calibration, even if an older base exists.
        if cmp -s "$WORK/$name.compare" "$WORK/$name.template"; then
            if ! cmp -s "$base" "$template"; then
                if [ ! -d "$base" ] &&
                    cp "$template" "$base.opencreator-new" 2>>"$LOG" &&
                    mv "$base.opencreator-new" "$base" 2>>"$LOG"; then
                    log "$name: current config, baseline synchronized"
                else
                    rm -f "$base.opencreator-new"
                    CONFLICTS="$CONFLICTS $name"
                    log "$name: CONFLICT -- could not synchronize baseline"
                fi
            fi
            continue
        fi
        merge_base=$base
        if [ ! -f "$base" ] || [ "$MIGRATION_PENDING" = 1 ]; then
            recover_baseline "$name" "$WORK/$name.compare"
            recovery_status=$?
            if [ "$recovery_status" = 0 ]; then
                merge_base="$WORK/$name.recovered"
                log "$name: recovered historical baseline"
            elif [ "$recovery_status" = 1 ] && [ -f "$base" ]; then
                if cmp -s "$base" "$template"; then
                    log "$name: unchanged template, preserving user edits"
                    continue
                fi
                # No exact match: retain the known base and merge user edits.
            else
                CONFLICTS="$CONFLICTS $name"
                log "$name: CONFLICT -- no safe historical baseline" \
                    "(lookup status $recovery_status); leaving live and base untouched"
                continue
            fi
        fi

        if ! normalize_config "$merge_base" "$WORK/$name.base" ||
            ! tr -d '\r' <"$live" >"$WORK/$name.live"; then
            CONFLICTS="$CONFLICTS $name"
            log "$name: CONFLICT -- could not prepare merge"
            continue
        fi
        diff -u "$WORK/$name.base" "$WORK/$name.template" \
            >"$WORK/$name.patch" 2>>"$LOG"
        diff_status=$?
        log "$name: template diff status $diff_status"
        if [ "$diff_status" -gt 1 ] ||
            ! cp "$WORK/$name.live" "$WORK/$name.merged"; then
            CONFLICTS="$CONFLICTS $name"
            log "$name: CONFLICT -- could not prepare template patch"
            continue
        fi
        # BusyBox patch has no -o or --no-backup-if-mismatch. Only a
        # successful complete merge reaches live; preserve failures in LOG.
        if patch "$WORK/$name.merged" <"$WORK/$name.patch" \
            >"$WORK/$name.patchlog" 2>&1; then
            :
        else
            patch_status=$?
            CONFLICTS="$CONFLICTS $name"
            log "$name: CONFLICT -- patch failed (status $patch_status)"
            cat "$WORK/$name.patchlog" >>"$LOG"
            continue
        fi
        if publish_config "$WORK/$name.merged" "$template" "$live" "$base" \
            >>"$LOG" 2>&1; then
            log "$name: merged"
            CHANGED=1
        else
            CONFLICTS="$CONFLICTS $name"
            log "$name: CONFLICT -- publication failed; live/base require resolution"
        fi
    done
}

# Every config is safe before either marker is published. Record the migration
# first; a failed commit publication leaves a HEAD mismatch for the next retry.
record_merge_success() {
    [ -z "$CONFLICTS" ] || return
    if ! printf '%s\n' "$MERGE_VERSION" >"$MERGE_VERSION_FILE.new" ||
        [ -d "$MERGE_VERSION_FILE" ] ||
        ! mv "$MERGE_VERSION_FILE.new" "$MERGE_VERSION_FILE"; then
        rm -f "$MERGE_VERSION_FILE.new"
        CONFLICTS="$CONFLICTS config-state"
        return
    fi
    if [ "$#" -gt 0 ]; then
        if ! printf '%s\n' "$1" >"$APPLIED.new" ||
            [ -d "$APPLIED" ] || ! mv "$APPLIED.new" "$APPLIED"; then
            rm -f "$APPLIED.new"
            CONFLICTS="$CONFLICTS config-state"
        fi
    fi
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

# LoopScript's own files: startup scripts, firmwareExe, the tunnel launcher,
# the Moonraker component, the Fluidd layout and the nginx snippets. Each
# folder is copied next to the live one, the new files are laid over the
# copy (user-added files stay) and it is swapped in, so running scripts (this
# one too) keep reading their old copy; the new ones run from the next boot.
# $OCDIR/.installed/<part>.md5 lists what was installed (shared with the
# installer): a listed file opencreator-fs dropped is removed if unchanged.
overlay_dir() {  # overlay_dir SRC DEST MANIFEST: copy SRC's files over DEST
    find "$1" -type f | sed "s#^$1/##" | while IFS= read -r f; do
        mkdir -p "$2/$(dirname "$f")"
        cp -p "$1/$f" "$2/$f"
        echo "$(md5sum <"$1/$f" | cut -d' ' -f1)  $f"
    done >"$3.new"
    if [ -f "$3" ]; then
        while IFS= read -r line; do
            f=${line#*  }
            [ -f "$1/$f" ] || [ ! -f "$2/$f" ] && continue
            [ "$(md5sum <"$2/$f" | cut -d' ' -f1)  $f" = "$line" ] && rm -f "$2/$f"
        done <"$3"
    fi
    return 0
}
part_current() {  # part_current SRC DEST: every SRC file already in DEST
    (cd "$1" && find . -type f) | while IFS= read -r f; do
        cmp -s "$1/$f" "$2/$f" || exit 1
    done
}
sync_loopscript() {
    src=$CLONE/fs/usr/data
    ls_changed=0
    mkdir -p "$OCDIR/.installed"
    for part in startup firmware tunneled moonraker fluidd plugin-manager; do
        [ -d "$src/opencreator/$part" ] || continue
        part_current "$src/opencreator/$part" "$OCDIR/$part" && continue
        rm -rf "$OCDIR/$part.new" "$OCDIR/$part.old"
        if [ -d "$OCDIR/$part" ]; then
            cp -a "$OCDIR/$part" "$OCDIR/$part.new" || { log "$part: copy failed"; continue; }
        fi
        manifest=$OCDIR/.installed/$part.md5
        overlay_dir "$src/opencreator/$part" "$OCDIR/$part.new" "$manifest" ||
            { log "$part: copy failed"; rm -rf "$OCDIR/$part.new"; continue; }
        case $part in
            startup) chmod 755 "$OCDIR/$part.new/startup.sh" "$OCDIR/$part.new"/scripts/*.sh ;;
            firmware) chmod 755 "$OCDIR/$part.new/firmwareExe" ;;
            plugin-manager) chmod 755 "$OCDIR/$part.new/oc-plugin" ;;
            # Executable means tunnel mode; keep whichever mode is set.
            tunneled) if [ -x "$OCDIR/tunneled/tunneled.sh" ]; then mode=755; else mode=644; fi
                      chmod "$mode" "$OCDIR/$part.new/tunneled.sh" ;;
        esac
        [ ! -d "$OCDIR/$part" ] || mv "$OCDIR/$part" "$OCDIR/$part.old"
        mv "$OCDIR/$part.new" "$OCDIR/$part"
        mv "$manifest.new" "$manifest"
        rm -rf "$OCDIR/$part.old"
        log "loopscript $part: updated"
        ls_changed=1
    done
    if ! cmp -s "$src/opencreator/version.txt" "$OCDIR/version.txt"; then
        cp "$src/opencreator/version.txt" "$OCDIR/version.txt"
    fi
    for conf in "$src"/nginx/conf.d/*.conf; do
        [ -f "$conf" ] || continue
        cmp -s "$conf" "$NGINX_CONF_D/$(basename "$conf")" && continue
        mkdir -p "$NGINX_CONF_D"
        cp "$conf" "$NGINX_CONF_D/" && log "nginx $(basename "$conf"): updated" && ls_changed=1
    done
    # Only while the LoopScript launcher is in place (shell script, not
    # FlashForge's ELF), so a rollback to stock is never undone.
    if [ "$(dd if="$FIRMWARE_EXE" bs=1 skip=1 count=3 2>/dev/null)" != ELF ] &&
        ! cmp -s "$OCDIR/firmware/firmwareExe" "$FIRMWARE_EXE"; then
        cp "$OCDIR/firmware/firmwareExe" "$FIRMWARE_EXE.new" &&
            chmod 755 "$FIRMWARE_EXE.new" && sync &&
            mv "$FIRMWARE_EXE.new" "$FIRMWARE_EXE" && log "firmwareExe: updated" && ls_changed=1
    fi
    sync
    if [ "$ls_changed" = 1 ]; then
        curl -fsS --max-time 10 -X POST -H 'Content-Type: application/json' \
            -d '{"script": "RESPOND MSG=\"OpenCreator startup files updated; they take effect after the next reboot.\""}' \
            "$MOONRAKER_API/printer/gcode/script" >/dev/null 2>&1
    fi
}

apply_clone() {
    head=$(git -C "$CLONE" rev-parse HEAD 2>/dev/null) || return
    # First run: the installed files came from this clone (or are newer, if
    # changed by hand), so only record where it is; sync from the next update.
    if [ ! -f "$LOOPSCRIPT_APPLIED" ]; then
        log "LoopScript files: tracking from opencreator-fs $head"
        echo "$head" >"$LOOPSCRIPT_APPLIED"
    elif [ "$head" != "$(cat "$LOOPSCRIPT_APPLIED" 2>/dev/null)" ]; then
        log "syncing LoopScript files from opencreator-fs $head"
        sync_loopscript
        echo "$head" >"$LOOPSCRIPT_APPLIED"
    fi
    if [ "$head" = "$(cat "$APPLIED" 2>/dev/null)" ] &&
        [ "$MERGE_VERSION" = "$(cat "$MERGE_VERSION_FILE" 2>/dev/null)" ]; then
        return
    fi
    log "applying opencreator-fs $head"
    CHANGED=0
    CONFLICTS=""
    rm -rf "$WORK"
    merge_configs "$CLONE/fs/usr/data/config"
    record_merge_success "$head"
    rm -rf "$WORK"
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
if ! tar -xzf "$WORK/opencreator-fs.tar.gz" -C "$WORK"; then
    log "template archive extraction failed, giving up this boot"
    rm -rf "$WORK"
    exit 0
fi
TEMPLATE_DIR=$(find "$WORK" -maxdepth 1 -type d -name 'opencreator-fs-*')/fs/usr/data/config
if [ ! -d "$TEMPLATE_DIR" ]; then
    log "template dir missing after extract, giving up this boot"
    rm -rf "$WORK"
    exit 0
fi

CHANGED=0
CONFLICTS=""
merge_configs "$TEMPLATE_DIR"
record_merge_success

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
