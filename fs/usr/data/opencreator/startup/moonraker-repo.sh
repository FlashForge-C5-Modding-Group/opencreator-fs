#!/bin/sh
# Keeps the Moonraker checkout one that Moonraker's update manager accepts.
#   moonraker-repo.sh repair    at boot, before the components are linked in
#   moonraker-repo.sh exclude   before each launch, after plugins are synced
#   moonraker-repo.sh live      both, from the updater while Moonraker runs
# See config-docs/MOONRAKER_REPO.md.
MR=${OC_MOONRAKER:-/usr/prog/moonraker/moonraker}
URL=https://github.com/Arksine/moonraker.git
BRANCH=master
TL=/usr/data/opencreator/moonraker-timelapse
export PATH=$PATH:/opt/bin
# FlashForge's LD_LIBRARY_PATH breaks Entware's git
unset LD_LIBRARY_PATH

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') moonraker repo: $*"; }
g() { git -C "$MR" "$@"; }

command -v git >/dev/null 2>&1 || exit 0
[ -d "$MR" ] || exit 0

trust() {
    # a checkout copied in with another owner: git refuses every command in it
    if g rev-parse HEAD 2>&1 | grep -q "dubious ownership"; then
        git config --global --add safe.directory "$MR"
        log "trusted $MR (it has another owner)"
    fi
}

# a checkout git can't read at all: downloaded again, the old one put back
# if that fails. Moonraker can't run from it, so this may wait for the network.
reclone() {
    log "not a working git checkout; downloading Moonraker again"
    rm -rf "$MR.new"
    if git clone -q --depth 1 --branch "$BRANCH" --single-branch "$URL" "$MR.new"; then
        rm -rf "$MR.old"
        mv "$MR" "$MR.old" && mv "$MR.new" "$MR" || { log "could not swap in the new checkout"; return 1; }
        rm -rf "$MR.old"
        g config core.fileMode false
        # links that lived in the old checkout; the launcher makes its own again
        [ -f "$TL/component/timelapse.py" ] &&
            ln -sf "$TL/component/timelapse.py" "$MR/moonraker/components/timelapse.py"
        log "downloaded again"
    else
        rm -rf "$MR.new"
        log "download failed; trying again at the next boot"
        return 1
    fi
}

repair() {
    trust
    if [ ! -e "$MR/.git" ] || ! g rev-parse -q --verify HEAD >/dev/null 2>&1; then
        # never swapped out under a running Moonraker
        if [ "${1:-}" = live ]; then
            log "not a working git checkout; it's downloaded again at the next boot"
        else
            reclone
        fi
        return
    fi

    # the official remote, so "Failed to detect repo url" can't happen
    url=$(g remote get-url origin 2>/dev/null)
    case "$url" in
        *[Aa]rksine/moonraker|*[Aa]rksine/moonraker.git) ;;
        "") g remote add origin "$URL" && log "added origin $URL" ;;
        *) g remote set-url origin "$URL" && log "origin was $url, now $URL" ;;
    esac
    # a clone of one tag fetches only that tag
    if ! g config --get-all remote.origin.fetch | grep -q -e 'refs/heads/\*' -e "refs/heads/$BRANCH:"; then
        g config --replace-all remote.origin.fetch "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
        log "origin now fetches $BRANCH"
    fi

    # on a branch, at the same commit: the files don't change
    cur=$(g symbolic-ref -q --short HEAD)
    if [ -z "$cur" ]; then
        g checkout -q -B "$BRANCH" && log "detached HEAD: now on $BRANCH at the same commit"
        cur=$BRANCH
    fi
    # tracking origin, so "Failed to detect git branch" can't happen either.
    # Another branch someone checked out on purpose keeps its own.
    if [ "$cur" = "$BRANCH" ] && [ "$(g config "branch.$cur.remote")" != origin ]; then
        g config "branch.$cur.remote" origin
        g config "branch.$cur.merge" "refs/heads/$BRANCH"
        log "$BRANCH now tracks origin/$BRANCH"
    fi
}

# Our components and plugins' are links into the checkout, and Moonraker
# lists untracked files as a problem. Links only: a real untracked file is
# still shown.
exclude() {
    gitdir=$(g rev-parse --absolute-git-dir 2>/dev/null) || return 0
    file=$gitdir/info/exclude
    mkdir -p "$gitdir/info"
    touch "$file"
    sed '/^# opencreator links begin$/,/^# opencreator links end$/d' "$file" > "$file.tmp"
    {
        echo "# opencreator links begin"
        for link in "$MR"/moonraker/components/*; do
            [ -L "$link" ] || continue
            rel=moonraker/components/${link##*/}
            g ls-files --error-unmatch -- "$rel" >/dev/null 2>&1 || echo "/$rel"
        done
        echo "# opencreator links end"
    } >> "$file.tmp"
    mv "$file.tmp" "$file"
}

case "${1:-}" in
    repair) repair ;;
    exclude) exclude ;;
    live) repair live; exclude ;;
    *) echo "usage: moonraker-repo.sh repair|exclude|live"; exit 1 ;;
esac
exit 0
