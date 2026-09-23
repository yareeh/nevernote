# Shared helpers; source from other scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
DATA_DIR="${DATA_DIR:-$ROOT/data}"
JOPLIN_PROFILE="${JOPLIN_PROFILE:-$DATA_DIR/joplin-cli}"
ENEX_DIR="${ENEX_DIR:-$DATA_DIR/enex}"
IMPORT_MARKER="$JOPLIN_PROFILE/.enex-imported"

die() { echo "error: $*" >&2; exit 1; }

load_env() {
    [[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found; run: cp .env.example .env && \$EDITOR .env"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
}

require_env() {
    local v
    for v in "$@"; do
        [[ -n "${!v:-}" ]] || die "$v is not set in $ENV_FILE"
    done
}

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
