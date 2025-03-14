#!/bin/bash
# Function to display usage
usage() {
	  echo "Usage: $0 --build-root=<build-root> --sqfs-images '<sqfs1>:<mnt1> <sqfs2>:<mnt2> ..' -- <command>"
	  exit 1
}

# Initialize variables
BUILD_ROOT=""
SQFS_IMAGES=""

# Parse options using getopt
TEMP=$(getopt -o '' --long build-root: --long sqfs-images: -n "$0" -- "$@")
if [ $? -ne 0 ]; then
	  echo "Error parsing arguments" >&2
	  usage
fi

# Reset the positional parameters to the short options
eval set -- "$TEMP"

# Extract options
while true; do
	  case "$1" in
	      --build-root)
		        BUILD_ROOT="$2"
		        shift 2
		        ;;
	      --sqfs-images)
		        SQFS_IMAGES="$2"
		        shift 2
		        ;;
	      --)
		        shift
		        break
		        ;;
	      *)
		        echo "Unknown option: $1"
		        usage
		        ;;
	  esac
done

if [ -z "$BUILD_ROOT" ]; then
	  echo "Error: --build-root is required" >&2
	  usage
fi

if [ -z "$SQFS_IMAGES" ]; then
    # no images to mount, skip squashfs-mount
    exec "$@"
fi

read -ra array <<<"$SQFS_IMAGES"

if [ ${#array[@]} -eq 0 ]; then
    echo "no mountpoints specified, skip squashfs-mount"
    exec "$@"
fi

build_root_mounts=""
for elem in "${array[@]}"; do
	  mount_point=${elem#*:}
    sqfs=${elem%%:*}
    tmp_mount_point="${BUILD_ROOT}/tmp/mounts/${mount_point}"
	  mkdir -p ${tmp_mount_point}
    build_root_mounts="${build_root_mounts} ${sqfs}:${tmp_mount_point}"
done

squashfs-mount $build_root_mounts -- "$@"
