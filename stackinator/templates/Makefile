{% set pipejoiner = joiner('|') %}
-include Make.user

.PHONY: all generate-config clean

all: store.squashfs

spack-version:
	$(SANDBOX) $(SPACK) --version > $@

# Sanity check: confirm spack works and bootstrap the concretizer.
spack-setup: spack-version
	$(call banner,Spack setup)
	@printf "spack arch... " ; \
	arch="$$($(SANDBOX) $(SPACK) arch)"; \
	printf "%s\n" "$$arch"; \
	printf "spack version... "; \
	version="$$($(SANDBOX) $(SPACK) --version)"; \
	printf "%s\n" "$$version"; \
	printf "checking if spack concretizer works... "; \
	$(SANDBOX) $(SPACK_HELPER) -d spec zlib > $(BUILD_ROOT)/spack-bootstrap-output 2>&1; \
	if [ "$$?" != "0" ]; then \
		printf " failed, see %s\n" $(BUILD_ROOT)/spack-bootstrap-output; \
		exit 1; \
	fi; \
	printf " success\n"; \
	touch spack-setup

{% if pre_install_hook %}
pre-install: spack-setup
	$(call banner,Pre-install hook)
	$(SANDBOX) $(STORE)/pre-install-hook
	touch pre-install
{% endif %}

mirror-setup: spack-setup{% if pre_install_hook %} pre-install{% endif %}

	$(call banner,Build cache / mirror setup)
{% if cache %}
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) buildcache keys --install --trust --yes-to-all
{% if cache.key %}
	$(SANDBOX) $(SPACK) gpg trust --yes-to-all {{ cache.key }}
{% endif %}
{% endif %}
	touch mirror-setup

concretize: mirror-setup env/spack.yaml
	$(call banner,Concretize)
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) concretize
	touch concretize

# Clear MAKEFLAGS for the install. When run with `make -j`, GNU make advertises a
# jobserver in MAKEFLAGS. GNU make < 4.4 uses the legacy fd form (`--jobserver-auth=R,W`)
# and closes those fds before running a non-recursive recipe, so they are invalid in the
# spack process. Spack's jobserver probe validates them with `fcntl(fd, F_GETFD) != -1`,
# a C idiom that in Python *raises* OSError(EBADF) instead of returning -1 - so the
# install aborts with `[Errno 9] Bad file descriptor` (independent of Python version).
# Hiding MAKEFLAGS makes spack create its own FIFO jobserver sized by `config:build_jobs`.
# Outer-make `-j` no longer governs spack; set build_jobs to control parallelism (or use
# GNU make >= 4.4, whose `fifo:` jobserver spack parses correctly).
install: concretize
	$(call banner,Install packages)
	MAKEFLAGS= $(SANDBOX) $(SPACK) -e $(ENV_ROOT) install --jobs $(NJOBS)
	touch install

cache-push: install
	$(call banner,Push to build cache)
{% if push_to_cache and cache.key %}
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) buildcache create --rebuild-index --only=package alpscache \
	$$($(SANDBOX) $(SPACK_HELPER) -e $(ENV_ROOT) find --format '{name};{/hash};version={version}' \
	| grep -v -E '^({% for p in exclude_from_cache %}{{ pipejoiner() }}{{ p }}{% endfor %});'\
	| grep -v -E 'version=git\.'\
	| cut -d ';' -f2) 2>&1 \
	| awk -v f="$(BUILD_ROOT)/gpg.log" '/^gpg:/{print > f; next} /^==> Fetching/{next} {print; fflush()}'
{% endif %}
	touch cache-push

cleanup: cache-push
	$(call banner,Cleanup)
{% if cleanup == "build" %}
	$(SANDBOX) $(SPACK) gc --yes-to-all --keep-build-dependencies --except-environment $(ENV_ROOT)
{% elif cleanup == "runtime" %}
	$(SANDBOX) $(SPACK) gc --yes-to-all --except-environment $(ENV_ROOT)
{% endif %}
	touch cleanup

# Generate compiler-config.yaml for use by view and generate-config steps.
compiler-config.yaml: cleanup
	$(call banner,Generate compiler config)
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) python $(BUILD_ROOT)/compiler-config.py \
{% if system_gcc %}
		--system-packages=$(BUILD_ROOT)/config/packages.yaml \
{% endif %}
		$(BUILD_ROOT)/compiler-config.yaml{% if compiler_names %} {{ compiler_names | join(' ') }}{% endif %}

# Generate activate.sh and env.json for each environment view. All views are
# built in a single target so their output is not interleaved under make -j.
views: install compiler-config.yaml
{% for name, config in environments.items() %}
{% for view in config.views %}
	$(call banner,View: {{ view.name }})
	$(SANDBOX) mkdir -p $(STORE)/env/{{ view.name }}
	$(SANDBOX) sh -c '$(SPACK) env activate -d $(ENV_ROOT) --with-view {{ view.name }} --sh > $(STORE)/env/{{ view.name }}/activate.sh'
	$(SANDBOX) $(BUILD_ROOT)/envvars.py view \
		{% if view.extra.add_compilers %}--compilers=$(BUILD_ROOT)/compiler-config.yaml {% endif %}\
		--prefix_paths="{{ view.extra.prefix_string }}" \
		$(STORE)/env/{{ view.name }} \
		$(BUILD_ROOT)
{% endfor %}
{% endfor %}
	touch views

generate-config: install compiler-config.yaml
	$(call banner,Generate upstream spack config)
	$(SANDBOX) $(MAKE) -j1 -C generate-config

{% if modules %}
modules-done: install generate-config
	$(call banner,Generate modules)
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) module tcl refresh --upstream-modules --delete-tree --yes-to-all
	touch modules-done
{% endif %}

env-meta: generate-config views{% if modules %} modules-done{% endif %}

	$(call banner,Generate uenv metadata)
	$(SANDBOX) $(BUILD_ROOT)/envvars.py uenv \
		{% if modules %}--modules {% endif %}\
		--spack='{{ spack_meta.url }},{{ spack_meta.ref }},{{ spack_meta.commit }}' \
{% for pkg_repo in spack_meta.packages %}
		--spack-package-repo='{{ pkg_repo.name }},{{ pkg_repo.url }},{{ pkg_repo.ref }},{{ pkg_repo.commit }}' \
{% endfor %}
		$(STORE)
	touch env-meta

{% if post_install_hook %}
post-install: env-meta
	$(call banner,Post-install hook)
	$(SANDBOX) $(STORE)/post-install-hook
	touch post-install
{% endif %}

store.squashfs: env-meta{% if post_install_hook %} post-install{% endif %}{% if push_to_cache and cache.key %} cache-push{% endif %}

	$(call banner,Create squashfs image)
	$(SANDBOX) find $(STORE)/repos -type d -name __pycache__ -exec rm -r {} +
	$(SANDBOX) chmod -R a+rX $(STORE)
	$(SANDBOX) env -u SOURCE_DATE_EPOCH \
		"$$($(SANDBOX) $(SPACK_HELPER) -e $(ENV_ROOT) find --format='{prefix}' squashfs | head -n1)/bin/mksquashfs" \
		$(STORE) $@ -force-uid nobody -force-gid nobody \
		-all-time $$(date +%s) -no-recovery -noappend -Xcompression-level 3

clean:
	rm -rf -- spack-version spack-setup{% if pre_install_hook %} pre-install{% endif %} mirror-setup \
		concretize install cleanup{% if push_to_cache and cache.key %} cache-push{% endif %} \
		compiler-config.yaml views generate-config/.done \
		{% if modules %}modules-done {% endif %}env-meta{% if post_install_hook %} post-install{% endif %} \
		store.squashfs spack-bootstrap-output

include Make.inc
