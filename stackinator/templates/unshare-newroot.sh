#!/bin/bash

# This script uses unshare(1), rather than bubblewrap, to create a sandbox with
# a writable root.

_dir=$(readlink -f "$(dirname "${BASH_SOURCE[0]}")")

## Helper functions ##

fatal () {
    printf 'error: %s' $1 1>2
    exit 1
}

print_debug () {
    [[ -z "$UNS_DEBUG" ]] || printf '[debug] %s\n' $1
}

print_verbose () {
    [[ -z "$UNS_VERBOSE" ]] || printf '[verbose] %s\n' $1
}

## Namespace manipulation ##

newroot_make () {
    if [[ -e "$newroot" ]] && [[ ! -d "$newroot" ]]; then
        printf 'error: newroot: %s: exists but is not a directory' "$newroot" 1>&2
        exit 1
    fi
    if [[ -d "$newroot" ]]; then
        printf "removing existing: newroot: %s\n" "$newroot"
        rm -rf --one-file-system "$newroot"
    fi
    printf "creating: newroot: %s\n" "$newroot"
    mkdir "$newroot"

    # Create mount points in newroot for files in '/'.
    find / -maxdepth 1 -not -wholename '/' | while read f; do mk_mnt_p "$f"; done
}

newroot_init () {
    # Ensure that the newroot exists.
    [[ -d "$newroot" ]] || fatal 'newroot: %s: does not exist'

    # At this point, we should be masquerading as root, i.e., this process
    # should be inside a unique user and mount namespace. The intended use
    # is as follows.
    #
    # $ unshare --user --map-user-root --mount ./newroot.sh \
    #           env --ignore-environment PATH=/usr/bin:`pwd`/spack/bin make \
    #           store.squashfs [...]
    #
    # FIXME: check if we are masquerading as root in a user and mount
    #        namespace.

    # Claim the newroot, /tmp/$USER.newroot, in our unshared namespace by
    # recusrively bind-mounting it over itself.
    mount --rbind --make-private "$newroot" "$newroot"

    # We do the same with /tmp. You would think that because /tmp contains
    # /tmp/$USER.newroot and it's a recursive bind mount, we could claim both
    # same call. But, we know this causes pivot_root(2) to fail later with
    # EBUSY; thus, we claim it here to avoid potential issues with tools that
    # may be used later, e.g., chroot, unshare (nested), pivot_root(1).
    #
    # Note: unlike the bubblewrap workflow, our newroot exists in tmp; thus,
    # we can set {{build_path}} to /dev/shm/$USER.build and avoid mounting
    # {{ build_path }}/tmp to /tmp at build time.
    mount --rbind --make-private /tmp /tmp

    # Recursively bind mount host / top-level, i.e., depth 1, files to the
    # corresponding points created by mk_mount_p. Exclude both '/' itself and
    # {{ store }} to avoid losing write permissions to newroot at build time.
    find / -maxdepth 1 \
           ! -wholename '/' -and ! -wholename '{{ store }}' \
               | while read f; do mount_ "$f"; done

    # Create the store mount point, e.g., /user-environment
    mkdir -p "${newroot}/${store_path}"

    # Create the build directory's store path. This is done later in Make.inc;
    # however we need it now to bind it to the store mount point.
    mkdir -p "${newroot}/${build_path}/store"
    mount -B --make-private "${newroot}/${build_path}/store" "${newroot}/${store_path}"

    # Create a TMPFS 'fake' home directory that Spack can write to. This file
    # is intentionally lost to the ether, to avoid re-using any
    # related configurations spack may write at build-time.
    #
    # Note, unlike manipulating Spack to write these configs to `/dev/null`,
    # we allow spack to write to a temporary file. We found this useful when
    # manipulating bootstrap and mirrors URLs at make/build time.
    mkdir -p "${newroot}/${spack_user_path}"
    mount -t tmpfs none "${newroot}/${spack_user_path}"
}

mk_mnt_p() {
    # Check if the src file is a directory. We do not care if a directory
    # is a symlink; we will follow the link via readlink and the absolute path
    # to the destination mount point."
    if [[ -d $1 ]]; then
        mkdir "${newroot}$1"
    else
        touch "${newroot}$1"
    fi
}

# Mount: bind, recursive, private.
mount_ () {
    f=$(readlink_f "$1")
    mount --rbind --make-private "$f" "${newroot}$1"
}


# Return absolute path if symlink.
readlink_f () {
    if [[ -L $1 ]]; then
        echo "$(readlink -f "$1")"
    else
        echo "$1"
    fi
}

newroot={{newroot}}
build_path={{build_path}}
store_path={{store}}
spack_user_path=/fake-home

# These variables should be set via jinja2 at this point; otherwise, error.
[[ -n "$newroot" ]]    || fatal 'var: NEWROOT: empty'
[[ -n "$build_path" ]] || fatal 'var: SOFTWARE_STACK_PROJECT: empty'
[[ -n "$store_path" ]] || fatal 'var: STORE: empty'
[[ -n "$spack_user_path" ]] || fatal 'var: SPACK_USER_CONFIG_PATH: empty'

if [[ -n "$UNS_DEBUG" ]]; then
    set -xe
fi

# Create the newroot and list the mount points.
newroot_make
find "$newroot"

# Claim newroot and bind files to newroot.
newroot_init

# "Pivot" the root and exec to command, e.g., `env [...] make store.squashfs`.
exec unshare --root="$newroot" --wd="$build_path" $@
