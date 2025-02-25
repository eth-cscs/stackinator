#!/bin/bash

set -euo pipefail
args=()
shopt -s dotglob

# from /user-environment/foo/bar/baz store /user-environment as _top_level
_top_level=$(echo $STORE | cut -d "/" -f 2 | xargs printf "/%s")

for d in /*; do
    # skip STORE
    if [ "$d" = "${_top_level}" ]; then
        continue
    fi
    # skip invalid symlinks, as they will break bwrap
    if [ ! -L "$d" ] || [ -e "$d" ]; then
        args+=("--dev-bind" "$d" "$d")
    fi
done

PS1="\[\e[36;1m\]build-env >>> \[\e[0m\]" bwrap "${args[@]}" "$@"
