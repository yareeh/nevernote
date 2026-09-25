#!/usr/bin/env bash
# Install/refresh the Quadlet unit that runs the viewer in rootless Podman.
# Reads DATA_DIR / VIEWER_PORT from .env (relative paths are relative to the
# repo root). Safe to rerun; `make viewer-up` builds the image first.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
QUADLET_DIR="$CONFIG/containers/systemd"
QUADLET="$QUADLET_DIR/nevernote.container"
LEGACY_UNIT="$CONFIG/systemd/user/nevernote.service"

die() { echo "error: $*" >&2; exit 1; }

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
abspath() { [[ "$1" == /* ]] && echo "$1" || echo "$ROOT/${1#./}"; }
DATA_DIR="$(abspath "${DATA_DIR:-data/viewer}")"
PORT="${VIEWER_PORT:-8765}"

command -v podman >/dev/null || die "podman is not installed; run: sudo apt install podman uidmap slirp4netns"
command -v systemctl >/dev/null || die "systemd not available"
[[ -f "$DATA_DIR/index.sqlite" ]] || die "no index in $DATA_DIR; run: make refresh"
if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != yes ]]; then
    echo "warning: lingering is off, so the viewer stops when you log out and won't" >&2
    echo "         start at boot. Enable with: sudo loginctl enable-linger $USER" >&2
fi

# The container's `viewer` user (10001) runs as subuid start + 10001 on the
# host (UserNS=nomap). Give that uid read access to the index, and to files
# `make refresh` writes later (default ACL). Nothing else in data/ is readable.
SUBUID_FILE="${SUBUID_FILE:-/etc/subuid}"
subuid_start="$(awk -F: -v u="$USER" '$1 == u { print $2; exit }' "$SUBUID_FILE" 2>/dev/null || true)"
[[ -n "$subuid_start" ]] || die "no subuid range for $USER in $SUBUID_FILE (needed for rootless Podman)"
VIEWER_HOST_UID=$((subuid_start + 10001))
command -v setfacl >/dev/null || die "setfacl is not installed; run: sudo apt install acl"
setfacl -R -m "u:$VIEWER_HOST_UID:rX" "$DATA_DIR"
setfacl -R -d -m "u:$VIEWER_HOST_UID:rX" "$DATA_DIR"
# Parents need no ACL: Podman bind-mounts DATA_DIR itself, so the container
# never traverses ~/, ~/git or data/.

# The pre-container version ran as a plain user unit with the same name.
if [[ -f "$LEGACY_UNIT" ]]; then
    systemctl --user disable --now nevernote.service >/dev/null 2>&1 || true
    rm -f "$LEGACY_UNIT"
    echo "Removed the old plain unit $LEGACY_UNIT"
fi

mkdir -p "$QUADLET_DIR"
sed -e "s|@DATA_DIR@|$DATA_DIR|g" -e "s|@PORT@|$PORT|g" \
    "$ROOT/deploy/nevernote.container" > "$QUADLET"
systemctl --user daemon-reload  # runs Podman's generator -> nevernote.service
echo "Installed $QUADLET"
echo "  DATA_DIR=$DATA_DIR (mounted read-only; readable by container uid $VIEWER_HOST_UID)"
echo "  PORT=$PORT"
echo "Viewer URL: http://$(hostname -I | awk '{print $1}'):$PORT"
