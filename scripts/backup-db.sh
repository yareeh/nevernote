#!/usr/bin/env bash
# Dump the Joplin Server Postgres DB to data/backups/.
source "$(dirname "$0")/lib.sh"
load_env
mkdir -p "$DATA_DIR/backups"
out="$DATA_DIR/backups/joplin-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose --project-directory "$ROOT" exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$out"
[[ -s "$out" ]] || die "backup is empty: $out"
echo "Wrote $out"
