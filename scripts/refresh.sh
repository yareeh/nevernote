#!/usr/bin/env bash
# make refresh: pull changes from Evernote, rebuild the viewer's index, and keep
# exactly one verified, compressed copy of the full ENEX export.
#
#   1. evernote-backup sync                  (data/evernote/en_backup.db)
#   2. export to a temporary dir             (data/.enex-refresh, ~23 GB, removed at the end)
#   3. enex-viewer index                     (data/viewer; atomic swap, the running viewer keeps serving)
#   4. tar | zstd -> data/archive/.enex-DATE.tar.zst.tmp, verified (zstd -t, file count)
#   5. rename to enex-DATE.tar.zst, then delete older archives
#
# On any failure the temporary export and partial archive are removed and the
# previous archive is kept.
#
# --from DIR: skip sync/export and use an existing export (not deleted).
# Tests override the steps with REFRESH_SYNC_CMD / REFRESH_EXPORT_CMD /
# REFRESH_INDEX_CMD (run with $WORK set) and DATA_ROOT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${DATA_ROOT:-$ROOT/data}"
DB="$DATA/evernote/en_backup.db"
ARCHIVE_DIR="$DATA/archive"
VIEWER_DIR="$DATA/viewer"
TMP_ARCHIVE=""
OWN_WORK=1
WORK="$DATA/.enex-refresh"

die() { echo "error: $*" >&2; exit 1; }

if [[ "${1:-}" == "--from" ]]; then
    [[ -d "${2:-}" ]] || die "--from needs an existing export directory"
    WORK="$(cd "$2" && pwd)"
    OWN_WORK=0
fi
export WORK DATA_ROOT="$DATA"

cleanup() {
    [[ -n "$TMP_ARCHIVE" ]] && rm -f "$TMP_ARCHIVE"
    if (( OWN_WORK )); then rm -rf "$WORK"; fi
}
trap cleanup EXIT

step() { echo "==> $*"; }

run_step() { # name, override-var, default command...
    local override="$2"
    shift 2
    if [[ -n "${!override:-}" ]]; then
        bash -c "${!override}"
    else
        "$@"
    fi
}

command -v zstd >/dev/null || die "zstd is not installed"
umask 077

if (( OWN_WORK )); then
    step "sync from Evernote"
    run_step sync REFRESH_SYNC_CMD \
        uv run --project "$ROOT" evernote-backup sync --use-system-ssl-ca -d "$DB"
    step "export to $WORK"
    rm -rf "$WORK"
    run_step export REFRESH_EXPORT_CMD \
        uv run --project "$ROOT" evernote-backup export -d "$DB" --add-guid "$WORK"
fi

count="$(find "$WORK" -type f -name '*.enex' ! -name '._*' | wc -l)"
(( count > 0 )) || die "no .enex files in $WORK"

step "index $count notebook(s) into $VIEWER_DIR"
run_step index REFRESH_INDEX_CMD \
    uv run --project "$ROOT" enex-viewer index --enex-dir "$WORK" --data-dir "$VIEWER_DIR"

step "archive"
mkdir -p "$ARCHIVE_DIR"
chmod 700 "$ARCHIVE_DIR"
name="enex-$(date +%F).tar.zst"
TMP_ARCHIVE="$ARCHIVE_DIR/.$name.tmp"
tar -C "$WORK" --exclude='._*' -cf - . | zstd -q -T0 -12 -o "$TMP_ARCHIVE" -f
zstd -q -t "$TMP_ARCHIVE" || die "archive failed zstd integrity check"
archived="$(tar -I zstd -tf "$TMP_ARCHIVE" | grep -c '\.enex$' || true)"
[[ "$archived" == "$count" ]] || die "archive has $archived .enex files, expected $count"

mv -f "$TMP_ARCHIVE" "$ARCHIVE_DIR/$name"
TMP_ARCHIVE=""
chmod 600 "$ARCHIVE_DIR/$name"
for old in "$ARCHIVE_DIR"/enex-*.tar.zst; do
    [[ "$old" == "$ARCHIVE_DIR/$name" ]] || rm -f "$old"
done
echo "Archived $count notebook(s): $ARCHIVE_DIR/$name ($(du -h "$ARCHIVE_DIR/$name" | cut -f1))"
