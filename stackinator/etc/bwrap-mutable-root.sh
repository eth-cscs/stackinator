#!/bin/bash
args=()
shopt -s dotglob
for d in /*; do
    # skip invalid symlinks, as they will break bwrap
    if [ ! -L "$d" ] || [ -e "$d" ]; then
        args+=("--dev-bind" "$d" "$d")
    fi
done
PS1="\[\e[36;1m\]build-env >>> \[\e[0m\]" bwrap "${args[@]}" "$@"

