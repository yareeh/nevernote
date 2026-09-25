# Evernote backup + read-only web viewer for the ENEX exports.
#   make setup
#   make evernote-init evernote-sync evernote-export   # -> data/enex/*.enex
#   make viewer-up                                     # -> http://<this box>:8765
SHELL := /bin/bash
DB := data/evernote/en_backup.db
# --use-system-ssl-ca on network commands: see override-dependencies in
# pyproject.toml (thrift 0.24.0 rejects evernote-backup's bundled CA file).
EB := uv run evernote-backup
SC := systemctl --user
UNIT := nevernote.service

.PHONY: help setup evernote-init evernote-sync evernote-export \
        viewer-install viewer-up viewer-down viewer-status viewer-logs \
        viewer-uninstall refresh dev check audit

##@ Operating

help: ## show this list
	@sed -n '1,/^SHELL/p' Makefile | grep '^#' | sed 's/^# \{0,1\}//'
	@awk 'BEGIN {FS = ":.*## "} \
	    /^##@ / {printf "\n%s\n", substr($$0, 5)} \
	    /^[a-z-]+:.*## / {printf "  %-17s %s\n", $$1, $$2}' Makefile

setup: ## install evernote-backup and the viewer's dev environment (uv)
	uv sync

evernote-init: ## log in to Evernote (OAuth URL is printed) and create the backup DB
	mkdir -p data/evernote && chmod 700 data  # the archive is private
	$(EB) init-db --use-system-ssl-ca -d $(DB)
	chmod 600 $(DB)  # holds the Evernote login token
evernote-sync: ## download/refresh everything from Evernote into the backup DB
	$(EB) sync --use-system-ssl-ca -d $(DB)
refresh: ## sync, re-index the viewer and replace the compressed ENEX archive in data/archive/
	scripts/refresh.sh
evernote-export: ## write one .enex per notebook (with note GUIDs) into data/enex/
	$(EB) export -d $(DB) --add-guid --overwrite data/enex/

viewer-install: ## install/refresh the systemd user service from .env (starts on boot)
	deploy/install-service.sh
viewer-up: ## (re)install and (re)start the viewer on this host
	deploy/install-service.sh
	$(SC) restart $(UNIT)
viewer-down: ## stop the viewer (it still starts on boot; see viewer-uninstall)
	$(SC) stop $(UNIT)
viewer-status: ## show whether the viewer is running
	$(SC) --no-pager status $(UNIT)
viewer-logs: ## follow viewer logs
	journalctl --user -u $(UNIT) -f
viewer-uninstall: ## stop the viewer and remove the service (keeps data/)
	-$(SC) disable --now $(UNIT)
	rm -f $${XDG_CONFIG_HOME:-$$HOME/.config}/systemd/user/$(UNIT)
	$(SC) daemon-reload

##@ Development

dev: ## run the viewer locally without Docker (env ENEX_DIR, PORT)
	uv run enex-viewer serve

check: ## lint, type-check and test
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pytest -q

audit: ## fail on known vulnerabilities in any locked dependency (pip-audit)
	uv export --color never --frozen --all-groups --no-emit-project --format requirements-txt \
	    | uv run pip-audit --disable-pip --require-hashes --strict -r /dev/stdin
