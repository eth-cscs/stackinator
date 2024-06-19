#!/bin/bash

root=$(pwd)
input_path=${root}/data/arbor-uenv
scratch_path=${root}/scratch
mount_path=${scratch_path}/user-environment
echo "===== setting up test mount path ${mount_path}"
rm -rf ${mount_path}

mkdir -p ${scratch_path}
cp -R ${input_path} ${mount_path}
meta_path=${mount_path}/meta/env.json
echo "===== input meta/env.json {meta_path}"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sed -i "s|@@mount@@|${mount_path}|g" ${meta_path}
else
    sed -i '' "s|@@mount@@|${mount_path}|g" ${meta_path}
fi

echo "===== running spack on develop"
../stackinator/etc/envvars.py spack ${mount_path}/env/develop

echo "===== running final meta data stage  ${mount_path}"

../stackinator/etc/envvars.py uenv ${mount_path}/ --modules --spack="https://github.com/spack/spack.git,releases/v0.20"

echo
echo "===== spack view"
echo
cat ${meta_path} | jq .views.spack

echo
echo "===== modules view"
echo
cat ${meta_path} | jq .views.modules
