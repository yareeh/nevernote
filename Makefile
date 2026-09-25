# Evernote backup.
#   make setup
#   make evernote-init evernote-sync evernote-export
SHELL := /bin/bash
DB := data/evernote/en_backup.db
EB := uv run evernote-backup

.PHONY: help setup evernote-init evernote-sync evernote-export

help:
	@sed -n '1,/^SHELL/p' Makefile | grep '^#' | sed 's/^# \{0,1\}//'
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/' | column -t -s$$'\t'

setup: ## install evernote-backup (uv)
	uv sync

evernote-init: ## log in to Evernote (OAuth URL is printed) and create the backup DB
	mkdir -p data/evernote
	$(EB) init-db -d $(DB)
evernote-sync: ## download/refresh everything from Evernote into the backup DB
	$(EB) sync -d $(DB)
evernote-export: ## write one .enex per notebook into data/enex/
	$(EB) export -d $(DB) --overwrite data/enex/
