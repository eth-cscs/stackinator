#!/bin/bash
args=()
shopt -s dotglob
for d in /*; do
  args+=("--dev-bind" "$d" "$d")
done
bwrap "${args[@]}" "$@"
