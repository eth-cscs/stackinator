-include Make.user

.PHONY: compilers packages generate-config clean spack-setup

all: packages

# Keep track of what Spack version was used.
spack-version:
	$(SANDBOX) $(SPACK) --version > $@

# Do some sanity checks: (a) are we not on cray, (b) are we using the same
# version as before, (c) ensure that the concretizer is bootstrapped to avoid a
# race where multiple processes start doing that.
spack-setup: spack-version
	@printf "spack arch... " ; \
	arch="$$($(SANDBOX) $(SPACK) arch)"; \
	printf "%s\n" "$$arch"; \
	case "$$arch" in \
		*cray*) \
			echo "You are running on Cray, which is usually a bad idea, since it turns Spack into modules mode. Try running in an clean environment with env -i."; \
			exit 1 \
			;; \
	esac; \
	printf "spack version... "; \
	version="$$($(SANDBOX) $(SPACK) --version)"; \
	printf "%s\n" "$$version"; \
	if [ "$$version" != "$$(cat spack-version)" ]; then \
		echo "The spack version seems to have been changed in the meantime... remove ./spack-version if that was intended"; \
		exit 1; \
	fi; \
	printf "checking if spack concretizer works... "; \
	$(SANDBOX) $(SPACK) spec zlib > /dev/null; \
	printf "yup\n"

mirror-setup: spack-setup
	{% if cache.enabled %}
	$(SANDBOX) $(SPACK) buildcache keys --install --trust
	{% if cache.key %}
	$(SANDBOX) $(SPACK) gpg trust {{ cache.key }}
	{% endif %}
	{% endif %}
	touch mirror-setup

compilers: mirror-setup
	$(SANDBOX) $(MAKE) -C $@

generate-config: compilers
	$(SANDBOX) $(MAKE) -C $@

packages: compilers
	$(SANDBOX) $(MAKE) -C $@

modules: packages generate-config
	$(SANDBOX) $(SPACK) -C $(STORE)/config module tcl refresh --upstream-modules --delete-tree --yes-to-all

# Create a squashfs file from the installed software.
store.squashfs: packages generate-config
	$(SANDBOX) "$$($(SANDBOX) $(SPACK) -e ./compilers/bootstrap find --format='{prefix}' squashfs | head -n1)/bin/mksquashfs" $(STORE) $@ -all-root -no-recovery -noappend -Xcompression-level 3

# A backup of all the generated files during the build, useful for posterity,
# excluding the binaries themselves, since they're in the squashfs file
build.tar.gz: spack-version Make.user Make.inc Makefile | packages
	tar czf $@ $^ $$(find packages compilers config -maxdepth 2 -name Makefile -o -name '*.yaml')

# Clean generate files, does *not* remove installed software.
clean:
	rm -rf -- $(wildcard */*/spack.lock) $(wildcard */*/.spack-env) $(wildcard */*/Makefile) $(wildcard */*/generated) $(wildcard cache) $(wildcard compilers/*/config.yaml) $(wildcard compilers/*/packages.yaml) $(wildcard compilers/*/compilers.yaml) $(wildcard packages/*/config.yaml) $(wildcard packages/*/packages.yaml) $(wildcard packages/*/compilers.yaml)

include Make.inc
