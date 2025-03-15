#!/bin/bash

set -eu

env --ignore-environment \
    PATH=/usr/bin:/bin:{{ build_path }}/spack/bin \
    HOME=$HOME BUILD_ROOT={{ build_path }} \
    STORE={{ mount_path }} SPACK_SYSTEM_CONFIG_PATH={{ build_path }}/config \
    SPACK_USER_CACHE_PATH={{ build_path }}/cache \
    SPACK=spack SPACK_COLOR=always \
    SPACK_USER_CONFIG_PATH={% if spack_version>="0.23" %}~{% else %}/dev/null{% endif %} \
    LC_ALL=en_US.UTF-8 TZ=UTC SOURCE_DATE_EPOCH=315576060 \
    {% if use_bwrap %} {{ build_path }}/bwrap-mutable-root.sh --tmpfs ~ --bind {{ build_path }}/tmp /tmp -- {{ build_path }}/bwrap-store.sh {% endif %} \
    bash -noprofile -l
