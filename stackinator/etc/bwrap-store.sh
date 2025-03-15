#!/bin/bash

set -euo pipefail

echo "creating $STORE"
mkdir -p $STORE

bwrap --dev-bind / / \
      --bind $BUILD_ROOT $STORE \
      -- "$@"
