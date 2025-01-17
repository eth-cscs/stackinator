{% set pipejoiner = joiner('|') %}
-include Make.user

.PHONY: compilers environments generate-config clean spack-setup

all: environments

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
	$(SANDBOX) $(SPACK_HELPER) -d spec zlib > $(BUILD_ROOT)/spack-bootstrap-output 2>&1; \
	if [ "$$?" != "0" ]; then \
		printf " failed, see %s\n" $(BUILD_ROOT)/spack-bootstrap-output; \
		exit 1; \
	fi; \
	printf " success\n"; \
	touch spack-setup

pre-install: spack-setup
	$(SANDBOX) $(STORE)/pre-install-hook

mirror-setup: spack-setup{% if pre_install_hook %} pre-install{% endif %}

	{% if cache %}
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

environments: compilers
	$(SANDBOX) $(MAKE) -C $@

{% if modules %}
modules-done: environments generate-config
	$(SANDBOX) $(SPACK) -C $(BUILD_ROOT)/modules module tcl refresh --upstream-modules --delete-tree --yes-to-all
	touch modules-done
{% endif %}


env-meta: generate-config environments{% if modules %} modules-done{% endif %}

	$(SANDBOX) $(BUILD_ROOT)/envvars.py uenv {% if modules %}--modules{% endif %} --spack='{{ spack_meta.url }},{{ spack_meta.ref }},{{ spack_meta.commit }}' $(STORE)
	touch env-meta

post-install: env-meta
	{% if post_install_hook %}
	$(SANDBOX) $(STORE)/post-install-hook
	{% endif %}
	touch post-install

# Create a squashfs file from the installed software.
store.squashfs: post-install
	# clean up the __pycache__ paths in the repo
	$(SANDBOX) find $(STORE)/repo -type d -name __pycache__ -exec rm -r {} +
	$(SANDBOX) chmod -R a+rX $(STORE)
	$(SANDBOX) env -u SOURCE_DATE_EPOCH "$$($(SANDBOX) $(SPACK_HELPER) -e ./compilers/bootstrap find --format='{prefix}' squashfs | head -n1)/bin/mksquashfs" $(STORE) $@ -all-root -all-time $$(date +%s) -no-recovery -noappend -Xcompression-level 3

# Force push all built packages to the build cache
cache-force: mirror-setup
{% if cache.key %}
	$(warning ================================================================================)
	$(warning Generate the config in order to force push partially built compiler environments)
	$(warning if this step is performed with partially built compiler envs, you will)
	$(warning likely have to start a fresh build (but that's okay, because build caches FTW))
	$(warning ================================================================================)
	$(SANDBOX) $(MAKE) -C generate-config
	$(SANDBOX) $(SPACK) -C $(STORE)/config buildcache create --rebuild-index --only=package alpscache \
	$$($(SANDBOX) $(SPACK_HELPER) -C $(STORE)/config find --format '{name};{/hash};version={version}' \
	| grep -v -E '^({% for p in exclude_from_cache %}{{ pipejoiner() }}{{ p }}{% endfor %});'\
	| grep -v -E 'version=git\.'\
	| cut -d ';' -f2)
{% else %}
	$(warning "pushing to the build cache is not enabled. See the documentation on how to add a key: https://eth-cscs.github.io/stackinator/build-caches/")
{% endif %}

# A backup of all the generated files during the build, useful for posterity,
# excluding the binaries themselves, since they're in the squashfs file
build.tar.gz: spack-version Make.user Make.inc Makefile | environments
	tar czf $@ $^ $$(find environments compilers config -maxdepth 2 -name Makefile -o -name '*.yaml')

# Clean generate files, does *not* remove installed software.
clean:
	rm -rf -- $(wildcard */*/spack.lock) $(wildcard */*/.spack-env) $(wildcard */*/Makefile) $(wildcard */*/generated) $(wildcard cache) $(wildcard compilers/*/config.yaml) $(wildcard compilers/*/packages.yaml) $(wildcard compilers/*/compilers.yaml) $(wildcard environments/*/config.yaml) $(wildcard environments/*/packages.yaml) $(wildcard environments/*/compilers.yaml) post-install modules-done env-meta store.squashfs 

include Make.inc
