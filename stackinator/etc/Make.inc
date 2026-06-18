# vi: filetype=make

SPACK ?= spack
SPACK_HELPER := $(SPACK) --color=never

# Per-phase banners. Colored on a terminal (MAKE_TERMOUT), plain when piped.
ifeq ($(origin NO_COLOR),undefined)
ifneq ($(MAKE_TERMOUT),)
BANNER_COLOR := \033[1;93m
BANNER_RESET := \033[0m
endif
endif

# Usage: $(call banner,Human readable phase name)
banner = @printf '\n%b==> [stackinator] %s%b\n' '$(BANNER_COLOR)' '$(1)' '$(BANNER_RESET)'

ifndef STORE
$(error STORE should point to a Spack install root)
endif

ifeq ($(wildcard $(SPACK_SYSTEM_CONFIG_PATH)),)
$(error SPACK_SYSTEM_CONFIG_PATH = "$(SPACK_SYSTEM_CONFIG_PATH)" doesn't point to an existing directory)
endif

store:
	mkdir -p $(STORE)
