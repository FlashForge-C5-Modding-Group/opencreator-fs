#!/usr/bin/env bash
# One 0.1.x GitHub release per pushed commit, see README.md "Releases".
set -euo pipefail

after=${AFTER:?}
before=${BEFORE:-}
prefix=v0.1.

if [[ -z $before || $before =~ ^0+$ ]] || ! git merge-base --is-ancestor "$before" "$after" 2>/dev/null; then
    commits=$after
else
    commits=$(git rev-list --reverse --first-parent "$before..$after")
fi

last=-1
for tag in $(git tag -l "$prefix*"); do
    n=${tag#"$prefix"}
    if [[ $n =~ ^[0-9]+$ ]] && (( n > last )); then
        last=$n
    fi
done
next=$((last + 1))

for commit in $commits; do
    if [[ -n $(git tag --points-at "$commit" -l "$prefix*") ]]; then
        echo "$commit is already released"
        continue
    fi
    message=$(git log -1 --format=%B "$commit")
    if [[ $message =~ (^|[[:space:]])-nover([[:space:]]|$) ]]; then
        echo "$commit has -nover, not released"
        continue
    fi
    tag=$prefix$next
    printf '%s\n' "$message" | gh release create "$tag" --target "$commit" --title "${tag#v}" --notes-file -
    next=$((next + 1))
done
