#!/bin/bash



echo "====================================="
echo "=====     post install hook     ====="

mount_path=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

echo RUNNING IN $mount_path

echo
echo "=====   environment variabls    ====="
printenv

echo
echo "=====   touching    ====="

echo "$(date)" > "$mount_path/post"

echo "====================================="
