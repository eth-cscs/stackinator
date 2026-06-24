{% set pipejoiner = joiner('|') %}
-include Make.user

.PHONY: all generate-config clean

all: store.squashfs

# Sanity check: confirm spack works and bootstrap the concretizer.
spack-setup:
	$(call banner,bootstrap spack)
	arch="$$($(SANDBOX) $(SPACK) arch)"; \
	version="$$($(SANDBOX) $(SPACK) --version)"; \
	printf "spack arch:   ...  %s\n" "$$arch"; \
	printf "spack version....  %s\n" "$$version"; \
	printf "bootstrapping spack... "; \
	$(SANDBOX) $(SPACK_HELPER) bootstrap now > $(BUILD_ROOT)/spack-bootstrap-output 2>&1; \
	if [ "$$?" != "0" ]; then \
		printf " failed, see %s\n" $(BUILD_ROOT)/spack-bootstrap-output; \
		exit 1; \
	fi; \
	printf " success\n"; \
	touch spack-setup

pre-install: spack-setup
	$(call banner,pre-install hook)
{% if pre_install_hook %}
	$(SANDBOX) $(STORE)/pre-install-hook
{% else %}
	echo "no pre install hook"
{% endif %}
	touch pre-install

mirror-setup: pre-install

	$(call banner,build cache / mirror setup)
	{% if buildcache %}
	@echo "Pulling and trusting keys from configured buildcaches."
	$(SANDBOX) $(SPACK) buildcache keys --install --trust --yes-to-all
	{% endif %}
	@echo "Adding mirror gpg keys."
	{% for key_path in gpg_keys %}
	$(SANDBOX) $(SPACK)	gpg trust  --yes-to-all {{ key_path }}
	{% endfor %}
	@echo "Current mirror list:"
	$(SANDBOX) $(SPACK) mirror list
	touch mirror-setup

concretize: mirror-setup env/spack.yaml
	$(call banner,concretize)
	# --non-defaults marks non-default variants and settings in the concretizer output
	# --force is required to reconcretize when env/spack.yaml is changed
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) concretize --non-defaults --force
	touch concretize

# Clear MAKEFLAGS for the install. When run with `make -j`, GNU make advertises a
# jobserver in MAKEFLAGS. GNU make < 4.4 uses the legacy fd form (`--jobserver-auth=R,W`)
# and closes those fds before running a non-recursive recipe, so they are invalid in the
# spack process - leading to bad file descriptor crashes.
# Hiding MAKEFLAGS makes spack create its own FIFO jobserver sized by `config:build_jobs`.
install: concretize
	$(call banner,install packages)
	MAKEFLAGS= $(SANDBOX) $(SPACK) -e $(ENV_ROOT) install --jobs $(NJOBS)
	touch install

cache-push: install
	$(call banner,push to build cache)
{% if buildcache_push %}
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) buildcache create --only=package {{ buildcache }} \
	$$($(SANDBOX) $(SPACK_HELPER) -e $(ENV_ROOT) find --format '{name};{/hash};version={version}' \
	| grep -v -E '^({% for p in exclude_from_cache %}{{ pipejoiner() }}{{ p }}{% endfor %});'\
	| grep -v -E 'version=git\.'\
	| cut -d ';' -f2) 2>&1 \
	| awk -v f="$(BUILD_ROOT)/gpg.log" '/^gpg:/{print > f; next} /^==> Fetching/{next} {print; fflush()}'
{% endif %}
	touch cache-push

cleanup: cache-push
	$(call banner,garbage collection)
{% if cleanup == "build" %}
	$(SANDBOX) $(SPACK) gc --yes-to-all --keep-build-dependencies --except-environment $(ENV_ROOT)
{% elif cleanup == "runtime" %}
	$(SANDBOX) $(SPACK) gc --yes-to-all --except-environment $(ENV_ROOT)
{% else %}
	echo "no garbage collection requested"
{% endif %}
	touch cleanup

# Generate compiler-config.yaml for use by view and generate-config steps.
compiler-config.yaml: cleanup
	$(call banner,generate compiler config)
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
	$(call banner,view: {{ view.name }})
	$(SANDBOX) mkdir -p $(STORE)/env/{{ view.name }}
	$(SANDBOX) sh -c '$(SPACK) env activate -d $(ENV_ROOT) --with-view {{ view.name }} --sh > $(STORE)/env/{{ view.name }}/activate.sh'
	$(SANDBOX) $(BUILD_ROOT)/envvars.py view \
		{% if view.extra.add_compilers %}--compilers=$(BUILD_ROOT)/compiler-config.yaml --compiler-names={{ config.compiler | join(',') }} {% endif %}\
		--prefix_paths="{{ view.extra.prefix_string }}" \
		$(STORE)/env/{{ view.name }} \
		$(BUILD_ROOT)
{% endfor %}
{% endfor %}
	touch views

generate-config: install compiler-config.yaml
	$(call banner,generate upstream spack config)
	$(SANDBOX) $(MAKE) -j1 -C generate-config

modules-done: generate-config
	$(call banner,generate modules)
{% if modules %}
	{% for module_type in module_types %}
	$(SANDBOX) $(SPACK) -C $(BUILD_ROOT)/modules module {{ module_type }} refresh --upstream-modules --delete-tree --yes-to-all
	{% endfor %}
{% else %}
	echo "no modules in this uenv"
{% endif %}
	touch modules-done

env-meta: generate-config views modules-done

	$(call banner,generate uenv metadata)
	$(SANDBOX) $(BUILD_ROOT)/envvars.py uenv \
		{% if modules %}--modules {% endif %}\
		--spack='{{ spack_meta.url }},{{ spack_meta.ref }},{{ spack_meta.commit }}' \
{% for pkg_repo in spack_meta.packages %}
		--spack-package-repo='{{ pkg_repo.name }},{{ pkg_repo.url }},{{ pkg_repo.ref }},{{ pkg_repo.commit }}' \
{% endfor %}
		$(STORE)
	touch env-meta

post-install: env-meta
	$(call banner,post-install hook)
{% if post_install_hook %}
	$(SANDBOX) $(STORE)/post-install-hook
{% else %}
	echo "no post install hook"
{% endif %}
	touch post-install

# Force push all built packages to the build cache
cache-force: mirror-setup
{% if buildcache_push %}
	$(warning ================================================================================)
	$(warning Generate the config in order to force push partially built compiler environments)
	$(warning if this step is performed with partially built compiler envs, you will)
	$(warning likely have to start a fresh build (but that's okay, because build caches FTW))
	$(warning ================================================================================)
	$(SANDBOX) $(MAKE) -C generate-config
	$(SANDBOX) $(SPACK) --color=never -C $(STORE)/config buildcache create --only=package {{ buildcache_push }} \
	$$($(SANDBOX) $(SPACK_HELPER) -C $(STORE)/config find --format '{name};{/hash};version={version}' \
	| grep -v -E '^({% for p in exclude_from_cache %}{{ pipejoiner() }}{{ p }}{% endfor %});'\
	| grep -v -E 'version=git\.'\
	| cut -d ';' -f2)\
	| grep -Ev '^==> Fetching|^gpg:'
{% else %}
	$(warning "pushing to the build cache is not enabled. See the documentation on how to add a key: https://eth-cscs.github.io/stackinator/build-caches/")
{% endif %}

store.squashfs: env-meta post-install cache-push

	$(call banner,create squashfs image)
	$(SANDBOX) find $(STORE)/repos -type d -name __pycache__ -exec rm -r {} +
	$(SANDBOX) chmod -R a+rX $(STORE)
	$(SANDBOX) env -u SOURCE_DATE_EPOCH \
		"$$($(SANDBOX) $(SPACK_HELPER) -e $(ENV_ROOT) find --format='{prefix}' squashfs | head -n1)/bin/mksquashfs" \
		$(STORE) $@ -force-uid nobody -force-gid nobody \
		-all-time $$(date +%s) -no-recovery -noappend -Xcompression-level 3

clean:
	rm -rf -- spack-setup{% if pre_install_hook %} pre-install{% endif %} mirror-setup \
		concretize install cleanup{% if push_to_cache and cache.key %} cache-push{% endif %} \
		compiler-config.yaml views generate-config/.done \
		{% if modules %}modules-done {% endif %}env-meta{% if post_install_hook %} post-install{% endif %} \
		store.squashfs spack-bootstrap-output

include Make.inc
