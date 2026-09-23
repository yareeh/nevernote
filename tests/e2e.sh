#!/usr/bin/env bash
# End-to-end: throwaway server stack -> create user -> import sample ENEX ->
# sync -> fresh second client syncs and sees the notes (stands in for the Mac).
# Touches nothing of the real stack/data: own compose project, port, data dir.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT=my-joplin-e2e
WORK="$(mktemp -d)"
DATA_DIR="$WORK/data"
export ENV_FILE="$WORK/.env"

# Paths come from the env file, the same way .env.test configures its instance.
cat > "$ENV_FILE" <<ENV
COMPOSE_PROJECT_NAME=$PROJECT
DATA_DIR=$DATA_DIR
ENEX_DIR=$ROOT/tests/fixtures
APP_BASE_URL=http://localhost:22399
APP_PORT=22399
POSTGRES_USER=joplin
POSTGRES_DB=joplin
POSTGRES_PASSWORD=e2e-postgres-pw
JOPLIN_ADMIN_EMAIL=admin@localhost
JOPLIN_ADMIN_PASSWORD=quartz-meadow-lantern-42
JOPLIN_USER_EMAIL=e2e@example.com
JOPLIN_USER_PASSWORD=copper-river-falcon-17
JOPLIN_USER_NAME=E2E
IMPORT_OUTPUT_FORMAT=md
ENV

dc() { docker compose --project-directory "$ROOT" --env-file "$ENV_FILE" "$@"; }
cleanup() {
    if [[ -n "${KEEP:-}" ]]; then echo "KEEP set: stack $PROJECT and $WORK left in place"; return; fi
    dc down -v >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

dc up -d
"$ROOT/scripts/server-user.sh"
"$ROOT/scripts/server-user.sh"   # idempotent: admin already rotated, user exists
"$ROOT/scripts/joplin-configure.sh"
"$ROOT/scripts/import-enex.sh"

echo "--- second import must be refused"
if "$ROOT/scripts/import-enex.sh" 2>"$WORK/err"; then fail "second import was allowed"; fi
grep -q "already imported" "$WORK/err" || fail "unexpected error: $(cat "$WORK/err")"

echo "--- fresh client (the 'Mac') syncs down"
export JOPLIN_PROFILE="$DATA_DIR/second-client"
"$ROOT/scripts/joplin-configure.sh"
J() { "$ROOT/node_modules/.bin/joplin" --profile "$JOPLIN_PROFILE" "$@"; }
J sync
books="$(J ls /)"
echo "$books"
grep -q "Sample Notebook" <<<"$books" || fail "notebook missing on second client"
J use "Sample Notebook"
notes="$(J ls)"
echo "$notes"
grep -q "Grocery list" <<<"$notes" || fail "note 'Grocery list' missing"
grep -q "Trip ideas" <<<"$notes" || fail "note 'Trip ideas' missing"
body="$(J cat "Grocery list")"
grep -q "oat milk" <<<"$body" || fail "note body not converted: $body"
echo "PASS"
