# Evernote backup + read-only web viewer for the ENEX exports.
#   make setup
#   make evernote-init evernote-sync evernote-export   # -> data/enex/*.enex
#   make viewer-up                                     # -> http://<this box>:8765
SHELL := /bin/bash
DB := data/evernote/en_backup.db
EB := uv run evernote-backup
DC := docker compose

.PHONY: help setup evernote-init evernote-sync evernote-export \
        viewer-up viewer-down viewer-logs viewer-reindex dev check

help:
	@sed -n '1,/^SHELL/p' Makefile | grep '^#' | sed 's/^# \{0,1\}//'
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/' | column -t -s$$'\t'

setup: ## install evernote-backup and the viewer's dev environment (uv)
	uv sync

evernote-init: ## log in to Evernote (OAuth URL is printed) and create the backup DB
	mkdir -p data/evernote
	$(EB) init-db -d $(DB)
evernote-sync: ## download/refresh everything from Evernote into the backup DB
	$(EB) sync -d $(DB)
evernote-export: ## write one .enex per notebook (with note GUIDs) into data/enex/
	$(EB) export -d $(DB) --add-guid --overwrite data/enex/

viewer-up: ## build and start the viewer in Docker (restarts on boot)
	$(DC) up -d --build
	@echo "Viewer: http://$$(hostname -I | awk '{print $$1}'):$${VIEWER_PORT:-8765}"
viewer-down: ## stop the viewer
	$(DC) down
viewer-logs: ## follow viewer logs
	$(DC) logs -f viewer
viewer-reindex: ## restart the viewer; it re-indexes if the ENEX files changed
	$(DC) restart viewer

dev: ## run the viewer locally without Docker (env ENEX_DIR, PORT)
	uv run enex-viewer serve

check: ## lint, type-check and test
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pytest -q
