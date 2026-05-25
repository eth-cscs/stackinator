{% set pipejoiner = joiner('|') %}
-include Make.user

.PHONY: all generate-config clean

all: store.squashfs

spack-version:
	$(SANDBOX) $(SPACK) --version > $@

# Sanity check: confirm spack works and bootstrap the concretizer.
spack-setup: spack-version
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
	$(SANDBOX) $(STORE)/pre-install-hook
	touch pre-install
{% endif %}

mirror-setup: spack-setup{% if pre_install_hook %} pre-install{% endif %}

{% if cache %}
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) buildcache keys --install --trust
{% if cache.key %}
	$(SANDBOX) $(SPACK) gpg trust {{ cache.key }}
{% endif %}
{% endif %}
	touch mirror-setup

concretize: mirror-setup
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) concretize
	touch concretize

install: concretize
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) install
	touch install

cleanup: install
{% if cleanup == "build" %}
	$(SANDBOX) $(SPACK) gc --yes-to-all --keep-build-dependencies --except-environment $(ENV_ROOT)
{% elif cleanup == "runtime" %}
	$(SANDBOX) $(SPACK) gc --yes-to-all --except-environment $(ENV_ROOT)
{% endif %}
	touch cleanup

{% if push_to_cache and cache.key %}
cache-push: install
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) buildcache create --rebuild-index --only=package alpscache \
	$$($(SANDBOX) $(SPACK_HELPER) -e $(ENV_ROOT) find --format '{name};{/hash};version={version}' \
	| grep -v -E '^({% for p in exclude_from_cache %}{{ pipejoiner() }}{{ p }}{% endfor %});'\
	| grep -v -E 'version=git\.'\
	| cut -d ';' -f2)\
	| grep -Ev '^==> Fetching|^gpg:'
	touch cache-push
{% endif %}

# Generate compiler-config.yaml for use by view and generate-config steps.
compiler-config.yaml: cleanup
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) python $(BUILD_ROOT)/compiler-config.py \
		$(BUILD_ROOT)/compiler-config.yaml \
		{{ compiler_names | join(' ') }}

# Generate activate.sh and env.json for each environment view.
{% for name, config in environments.items() %}
{% for view in config.views %}
views/{{ view.name }}: install compiler-config.yaml
	mkdir -p $(dir $@)
	$(SANDBOX) mkdir -p $(STORE)/env/{{ view.name }}
	$(SANDBOX) sh -c '$(SPACK) env activate -d $(ENV_ROOT) --with-view {{ view.name }} --sh > $(STORE)/env/{{ view.name }}/activate.sh'
	$(SANDBOX) $(BUILD_ROOT)/envvars.py view \
		{% if view.extra.add_compilers %}--compilers=$(BUILD_ROOT)/compiler-config.yaml {% endif %}\
		--prefix_paths="{{ view.extra.prefix_string }}" \
		$(STORE)/env/{{ view.name }} \
		$(BUILD_ROOT)
	touch $@

{% endfor %}
{% endfor %}
views: {% for name, config in environments.items() %}{% for view in config.views %}views/{{ view.name }} {% endfor %}{% endfor %}

	touch views

generate-config: install compiler-config.yaml
	$(SANDBOX) $(MAKE) -j1 -C generate-config

{% if modules %}
modules-done: install generate-config
	$(SANDBOX) $(SPACK) -e $(ENV_ROOT) module tcl refresh --upstream-modules --delete-tree --yes-to-all
	touch modules-done
{% endif %}

env-meta: generate-config views{% if modules %} modules-done{% endif %}

	$(SANDBOX) $(BUILD_ROOT)/envvars.py uenv \
		{% if modules %}--modules {% endif %}\
		--spack='{{ spack_meta.url }},{{ spack_meta.ref }},{{ spack_meta.commit }}' \
		--spack-packages='{{ spack_meta.packages_url }},{{ spack_meta.packages_ref }},{{ spack_meta.packages_commit }}' \
		$(STORE)
	touch env-meta

{% if post_install_hook %}
post-install: env-meta
	$(SANDBOX) $(STORE)/post-install-hook
	touch post-install
{% endif %}

store.squashfs: env-meta{% if post_install_hook %} post-install{% endif %}{% if push_to_cache and cache.key %} cache-push{% endif %}

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
