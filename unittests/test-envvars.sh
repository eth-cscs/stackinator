#!/usr/bin/env bash

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

../stackinator/etc/envvars.py uenv ${mount_path}/ --modules --spack="https://github.com/spack/spack.git,releases/v0.20,abc123" --spack-package-repo="builtin,https://github.com/spack/spack-packages.git,develop,abc123"

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

echo
echo "===== test UENV_PACKAGE_REPOS with multiple package repos"
rm -rf ${mount_path}
mkdir -p ${scratch_path}
cp -R ${input_path} ${mount_path}
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sed -i "s|@@mount@@|${mount_path}|g" ${meta_in_path}
else
    sed -i '' "s|@@mount@@|${mount_path}|g" ${meta_in_path}
fi

../stackinator/etc/envvars.py view ${mount_path}/env/arbor /dev/shm/bcumming/arbor
../stackinator/etc/envvars.py view --prefix_paths="LD_LIBRARY_PATH=lib:lib64" ${mount_path}/env/develop /dev/shm/bcumming/arbor

../stackinator/etc/envvars.py uenv ${mount_path}/ \
    --spack="https://github.com/spack/spack.git,releases/v0.21,abc123def" \
    --spack-package-repo="my-packages,https://github.com/example/spack-packages.git,v1.0,abc123" \
    --spack-package-repo="other-packages,https://github.com/example/other-packages.git,main,def456"

UENV_PACKAGE_REPOS=$(cat ${meta_path} | jq -r '.views.spack.env.values.scalar.UENV_PACKAGE_REPOS')
echo "UENV_PACKAGE_REPOS=$UENV_PACKAGE_REPOS"
if [[ "$UENV_PACKAGE_REPOS" != "my-packages,other-packages" ]]; then
    echo "FAIL: expected my-packages,other-packages, got '${UENV_PACKAGE_REPOS}'"
    exit 1
fi

UENV_PACKAGE_REPO_MY_PACKAGES_URL=$(cat ${meta_path} | jq -r '.views.spack.env.values.scalar.UENV_PACKAGE_REPO_MY_PACKAGES_URL')
echo "UENV_PACKAGE_REPO_MY_PACKAGES_URL=$UENV_PACKAGE_REPO_MY_PACKAGES_URL"
if [[ "$UENV_PACKAGE_REPO_MY_PACKAGES_URL" != "https://github.com/example/spack-packages.git" ]]; then
    echo "FAIL: expected https://github.com/example/spack-packages.git, got '${UENV_PACKAGE_REPO_MY_PACKAGES_URL}'"
    exit 1
fi

echo "PASSED"

