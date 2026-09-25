#!/usr/bin/env bash
# Install/refresh the systemd *user* unit that runs the viewer on this host.
# Reads ENEX_DIR / DATA_DIR / VIEWER_PORT from .env (relative paths are
# relative to the repo root). Safe to rerun after editing .env.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/nevernote.service"

die() { echo "error: $*" >&2; exit 1; }

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
abspath() { [[ "$1" == /* ]] && echo "$1" || echo "$ROOT/${1#./}"; }
ENEX_DIR="$(abspath "${ENEX_DIR:-data/enex}")"
DATA_DIR="$(abspath "${DATA_DIR:-data/viewer}")"
PORT="${VIEWER_PORT:-8765}"

[[ -x "$ROOT/.venv/bin/enex-viewer" ]] || die "no .venv; run: make setup"
[[ -d "$ENEX_DIR" ]] || die "ENEX_DIR $ENEX_DIR does not exist; run make evernote-export or fix .env"
command -v systemctl >/dev/null || die "systemd not available"
if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != yes ]]; then
    echo "warning: lingering is off, so the viewer stops when you log out and won't" >&2
    echo "         start at boot. Enable with: sudo loginctl enable-linger $USER" >&2
fi

mkdir -p "$UNIT_DIR" "$DATA_DIR"
sed -e "s|@ROOT@|$ROOT|g" -e "s|@ENEX_DIR@|$ENEX_DIR|g" \
    -e "s|@DATA_DIR@|$DATA_DIR|g" -e "s|@PORT@|$PORT|g" \
    "$ROOT/deploy/nevernote.service.in" > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable nevernote.service >/dev/null
echo "Installed $UNIT"
echo "  ENEX_DIR=$ENEX_DIR"
echo "  DATA_DIR=$DATA_DIR"
echo "  PORT=$PORT"
echo "Viewer URL: http://$(hostname -I | awk '{print $1}'):$PORT"
