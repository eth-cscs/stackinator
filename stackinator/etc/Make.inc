# vi: filetype=make

SPACK ?= spack
SPACK_HELPER := $(SPACK) --color=never

ifndef STORE
$(error STORE should point to a Spack install root)
endif

ifeq ($(wildcard $(SPACK_SYSTEM_CONFIG_PATH)),)
$(error SPACK_SYSTEM_CONFIG_PATH = "$(SPACK_SYSTEM_CONFIG_PATH)" doesn't point to an existing directory)
endif

store:
	mkdir -p $(STORE)
