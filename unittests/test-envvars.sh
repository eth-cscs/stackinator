#!/bin/bash

root=$(pwd)
input_path=${root}/data/arbor-uenv
for p in man misc aclocal lib64 lib64/pkgconfig bin lib lib/pkgconfig lib/python3.11 lib/python3.11/site-packages share share/pkgconfig
do
    mkdir -p $input_path/env/develop/$p
done
for p in man misc aclocal bin lib lib/pkgconfig lib/python3.11 lib/python3.11/site-packages share share/pkgconfig
do
    mkdir -p $input_path/env/arbor/$p
done
scratch_path=${root}/scratch
mount_path=${scratch_path}/user-environment
echo "===== setting up test mount path ${mount_path}"
rm -rf ${mount_path}

mkdir -p ${scratch_path}
cp -R ${input_path} ${mount_path}
meta_path=${mount_path}/meta/env.json
meta_in_path=${mount_path}/meta/env.json.in
echo "===== input meta/env.json.in ${meta_in_path}"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sed -i "s|@@mount@@|${mount_path}|g" ${meta_in_path}
else
    sed -i '' "s|@@mount@@|${mount_path}|g" ${meta_in_path}
fi

echo "===== envvars view develop"
../stackinator/etc/envvars.py view ${mount_path}/env/arbor /dev/shm/bcumming/arbor
echo "===== envvars view arbor"
../stackinator/etc/envvars.py view --prefix_paths="LD_LIBRARY_PATH=lib:lib64" ${mount_path}/env/develop /dev/shm/bcumming/arbor

echo "===== all env.json files after running view meta generation"
find $scratch_path -name env.json

echo "===== running final meta data stage  ${mount_path}"

../stackinator/etc/envvars.py uenv ${mount_path}/ --modules --spack="https://github.com/spack/spack.git,releases/v0.20" --spack-packages="https://github.com/spack/spack.git,develop"

echo
echo "===== develop"
echo
cat ${meta_path} | jq .views.develop

echo
echo "===== arbor"
echo
cat ${meta_path} | jq .views.arbor

echo
echo "===== spack view"
echo
cat ${meta_path} | jq .views.spack

echo
echo "===== modules view"
echo
cat ${meta_path} | jq .views.modules

