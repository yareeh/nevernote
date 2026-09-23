# Shared helpers; source from other scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
[[ "$ENV_FILE" == /* ]] || ENV_FILE="$ROOT/$ENV_FILE"

die() { echo "error: $*" >&2; exit 1; }

abspath() { [[ "$1" == /* ]] && echo "$1" || echo "$ROOT/$1"; }

# Source the env file, then derive paths. DATA_DIR and ENEX_DIR may be set in
# the env file (relative paths are relative to the repo root), which is how
# .env and .env.test keep separate CLI profiles and inputs.
load_env() {
    [[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found; run: cp .env.example .env && \$EDITOR .env"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    DATA_DIR="$(abspath "${DATA_DIR:-data}")"
    ENEX_DIR="$(abspath "${ENEX_DIR:-$DATA_DIR/enex}")"
    JOPLIN_PROFILE="$(abspath "${JOPLIN_PROFILE:-$DATA_DIR/joplin-cli}")"
    IMPORT_MARKER="$JOPLIN_PROFILE/.enex-imported"
}

require_env() {
    local v
    for v in "$@"; do
        [[ -n "${!v:-}" ]] || die "$v is not set in $ENV_FILE"
    done
}

compose() { docker compose --project-directory "$ROOT" --env-file "$ENV_FILE" "$@"; }

joplin() {
    [[ -x "$ROOT/node_modules/.bin/joplin" ]] || die "Joplin CLI missing; run: make setup"
    "$ROOT/node_modules/.bin/joplin" --profile "$JOPLIN_PROFILE" "$@"
}

wait_for_server() {
    local url="${APP_BASE_URL%/}/api/ping" i
    for i in $(seq 90); do
        curl -sf "$url" >/dev/null 2>&1 && return 0
        sleep 2
    done
    die "Joplin Server not reachable at $url (is it up? does APP_BASE_URL point at this box?)"
}
