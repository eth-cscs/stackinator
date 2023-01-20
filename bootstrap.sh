#!/bin/bash


PYTHON=${PYTHON:-python3}

pyver=$($PYTHON -V | sed -n 's/Python \([0-9]\+\)\.\([0-9]\+\)\..*/\1.\2/p')

$PYTHON -m ensurepip --version &> /dev/null
epip=$?

export PATH=$(pwd)/external/usr/bin:$PATH

# Install pip for Python 3
if [ $epip -eq 0 ]; then
    $PYTHON -m ensurepip --root $(pwd)/external/ --default-pip
fi

export PYTHONPATH=$(pwd)/external:$(pwd)/external/usr/lib/python$pyver/site-packages:$PYTHONPATH

$PYTHON -m pip install --no-cache-dir -q --upgrade pip --target=external/

$PYTHON -m pip install --no-cache-dir -q -r requirements.txt --target=external/ --upgrade
