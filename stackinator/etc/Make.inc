# vi: filetype=make

SPACK ?= spack

SPACK_ENV = $(SPACK) -e $(dir $@)

ifndef STORE
$(error STORE should point to a Spack install root)
endif

ifeq ($(wildcard $(SPACK_SYSTEM_CONFIG_PATH)),)
$(error SPACK_SYSTEM_CONFIG_PATH = "$(SPACK_SYSTEM_CONFIG_PATH)" doesn't point to an existing directory)
endif

store:
	mkdir -p $(STORE)

# Concretization
%/spack.lock: %/spack.yaml %/config.yaml %/packages.yaml
	/usr/bin/time -f "\"%C\" took %e seconds." $(SPACK_ENV) concretize -f

# Generate Makefiles for the environment install
%/Makefile: %/spack.lock
	$(SPACK_ENV) env depfile --make-target-prefix $*/generated -o $@

# For generating {compilers,config,packages}.yaml files.
%.yaml: export SPACK_USER_CONFIG_PATH=$(abspath $(dir $@))
%.yaml:
	touch $@

# Because Spack doesn't know how to find compilers, we help it by getting the bin folder of gcc, clang, nvc given a install prefix
compiler_bin_dirs = $$(find $(1) '(' -name gcc -o -name clang -o -name nvc ')' -path '*/bin/*' '(' -type f -o -type l ')' -exec dirname {} +)
