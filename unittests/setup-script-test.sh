#!/bin/bash

root=$(pwd)
input_path=${root}/test-env
mount_path=${root}/test-mount
echo "===== setting up test mount path ${mount_path}"
rm -rf ${mount_path}
cp -R ${input_path} ${mount_path}
meta_path=${mount_path}/meta/env.json
echo "===== input meta/env.json {meta_path}"
#sed -i "s|@@mount@@|${mount_path}|g" ${meta_path}
sed -i '' "s|@@mount@@|${mount_path}|g" ${meta_path}

echo "===== running tool on  ${mount_path}"
./envvars.py ${mount_path}/ --modules --spack="https://github.com/spack/spack.git,releases/v0.20"

echo
echo "===== spack view"
echo
cat ${meta_path} | jq .views.spack

echo
echo "===== modules view"
echo
cat ${meta_path} | jq .views.modules
