#!/bin/bash


PYTHON=${PYTHON:-python3}
external_dir=$(dirname $0)/external

pyver=$($PYTHON -V | sed -n 's/Python \([0-9]\+\)\.\([0-9]\+\)\..*/\1.\2/p')

$PYTHON -m ensurepip --version &> /dev/null
epip=$?

export PATH=$external_dir/usr/bin:$PATH

# Install pip for Python 3
if [ $epip -eq 0 ]; then
    $PYTHON -m ensurepip --root $external_dir --default-pip
fi

export PYTHONPATH=$external_dir:$external_dir/usr/lib/python$pyver/site-packages:$PYTHONPATH

$PYTHON -m pip install --no-cache-dir -q --upgrade pip --target=$external_dir/

$PYTHON -m pip install --no-cache-dir -q -r $(dirname $0)/requirements.txt --target=$external_dir --upgrade
