# Evernote -> Joplin migration + self-hosted Joplin Server.
# Typical first run, in order:
#   make setup server-up server-user
#   make evernote-init evernote-sync evernote-export
#   make joplin-configure import
SHELL := /bin/bash
DB := data/evernote/en_backup.db
EB := uv run evernote-backup
JOPLIN := node_modules/.bin/joplin --profile data/joplin-cli

.PHONY: help setup server-up server-down server-logs server-user \
        evernote-init evernote-sync evernote-export \
        joplin-configure import sync status backup test

help:
	@sed -n '1,/^SHELL/p' Makefile | grep '^#' | sed 's/^# \{0,1\}//'
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/' | column -t -s$$'\t'

setup: ## install evernote-backup (uv) and Joplin CLI (npm), create .env
	uv sync
	npm ci --no-fund --no-audit
	@[[ -f .env ]] || { cp .env.example .env; chmod 600 .env; echo "Created .env - edit it now."; }

server-up: ## start Joplin Server + Postgres
	docker compose up -d
server-down: ## stop the server (data kept in the pgdata volume)
	docker compose down
server-logs: ## follow server logs
	docker compose logs -f app
server-user: ## rotate default admin password, create/activate your user
	scripts/server-user.sh

evernote-init: ## log in to Evernote (OAuth URL is printed) and create the backup DB
	mkdir -p data/evernote
	$(EB) init-db -d $(DB)
evernote-sync: ## download/refresh everything from Evernote into the backup DB
	$(EB) sync -d $(DB)
evernote-export: ## write one .enex per notebook into data/enex/
	$(EB) export -d $(DB) --overwrite data/enex/

joplin-configure: ## point the Joplin CLI profile at Joplin Server
	scripts/joplin-configure.sh
import: ## ONE-OFF: import all .enex files and sync (refuses to run twice)
	scripts/import-enex.sh
sync: ## re-run Joplin CLI sync (e.g. if the sync after import was interrupted)
	$(JOPLIN) sync
status: ## show CLI profile note/notebook counts
	$(JOPLIN) status

backup: ## pg_dump the server DB into data/backups/
	scripts/backup-db.sh

test: ## end-to-end test against a throwaway stack on port 22399
	tests/e2e.sh
