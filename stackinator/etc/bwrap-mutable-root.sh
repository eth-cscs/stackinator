#!/bin/bash
args=()
shopt -s dotglob
for d in /*; do
    # skip invalide symlinks, as they will break bwrap
    if [ ! -L "$d" ] || [ -e "$" ]; then
        args+=("--dev-bind" "$d" "$d")
    fi
done
bwrap "${args[@]}" "$@"
