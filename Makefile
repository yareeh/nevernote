# Evernote -> Joplin migration + self-hosted Joplin Server.
# Typical first run, in order:
#   make setup server-up server-user
#   make evernote-init evernote-sync evernote-export
#   make joplin-configure import
# Every target acts on the instance in ENV_FILE (default .env), e.g.
#   make ENV_FILE=.env.test status
SHELL := /bin/bash
ENV_FILE ?= .env
export ENV_FILE
DC := docker compose --env-file $(ENV_FILE)
DB := data/evernote/en_backup.db
EB := uv run evernote-backup

# Test instance: imports the sample notebooks from tmp/evernote, port 22301.
TEST_ENV := .env.test
TEST_PORT := 22301
TEST_HOST := $(shell hostname -I | awk '{print $$1}')

.PHONY: help setup server-up server-down server-logs server-user \
        evernote-init evernote-sync evernote-export \
        joplin-configure import sync status backup test \
        test-server test-server-reset

help:
	@sed -n '1,/^SHELL/p' Makefile | grep '^#' | sed 's/^# \{0,1\}//'
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/' | column -t -s$$'\t'

setup: ## install evernote-backup (uv) and Joplin CLI (npm), create .env
	uv sync
	npm ci --no-fund --no-audit
	@[[ -f .env ]] || { scripts/init-env.sh .env; echo "Now set JOPLIN_USER_EMAIL/NAME and APP_BASE_URL in .env"; }

server-up: ## start Joplin Server + Postgres
	$(DC) up -d
server-down: ## stop the server (data kept in the pgdata volume)
	$(DC) down
server-logs: ## follow server logs
	$(DC) logs -f app
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
	scripts/joplin.sh sync
status: ## show CLI profile note/notebook counts
	scripts/joplin.sh status

backup: ## pg_dump the server DB into $DATA_DIR/backups/
	scripts/backup-db.sh

test: ## end-to-end test against a throwaway stack on port 22399
	tests/e2e.sh

test-server: ## test instance: server on :22301 with tmp/evernote/*.enex imported
	@[[ -f $(TEST_ENV) ]] || scripts/init-env.sh $(TEST_ENV) \
	    COMPOSE_PROJECT_NAME=my-joplin-test \
	    APP_BASE_URL=http://$(TEST_HOST):$(TEST_PORT) APP_PORT=$(TEST_PORT) \
	    DATA_DIR=data-test ENEX_DIR=tmp/evernote \
	    JOPLIN_USER_EMAIL=test@localhost JOPLIN_USER_NAME=Test
	$(MAKE) ENV_FILE=$(TEST_ENV) server-up server-user joplin-configure import
test-server-reset: ## destroy the test instance (server DB volume + data-test/)
	docker compose --env-file $(TEST_ENV) down -v
	rm -rf data-test
