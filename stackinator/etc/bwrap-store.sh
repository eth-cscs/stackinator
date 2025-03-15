#!/bin/bash

set -euo pipefail

mkdir -p $STORE

bwrap --dev-bind / / \
      --bind ${BUILD_ROOT}/store $STORE \
      -- "$@"
