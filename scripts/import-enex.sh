#!/usr/bin/env bash
# One-off: import every ENEX file (one notebook each) into the CLI profile,
# verify nothing was dropped, then sync to Joplin Server. Refuses to run twice,
# since a second import duplicates every note. FORCE=1 overrides.
source "$(dirname "$0")/lib.sh"
load_env
fmt="${IMPORT_OUTPUT_FORMAT:-md}"
[[ "$fmt" == md || "$fmt" == html ]] || die "IMPORT_OUTPUT_FORMAT must be md or html, got '$fmt'"

if [[ -f "$IMPORT_MARKER" && "${FORCE:-0}" != 1 ]]; then
    die "ENEX already imported on $(head -1 "$IMPORT_MARKER"). Re-importing duplicates every note.
See README 'Starting over' if you really want to redo the migration."
fi

shopt -s nullglob
files=()
for f in "$ENEX_DIR"/*.enex; do
    # Skip macOS AppleDouble "._*" files that ride along when copying from a Mac.
    [[ "$(basename "$f")" == ._* ]] || files+=("$f")
done
(( ${#files[@]} )) || die "no .enex files in $ENEX_DIR; run: make evernote-export"

grep -q "my-joplin patch" "$ROOT/node_modules/joplin/app.js" \
    || die "Joplin CLI is unpatched and silently drops notes; run: npm ci"
[[ "$(joplin config sync.target 2>/dev/null)" == *9* ]] \
    || die "CLI not configured for Joplin Server; run: make joplin-configure"

# Total notes in the profile, from `joplin status` ("Note: synced/total").
note_total() { joplin status | awk -F'[:/ ]+' '/^Note:/ {print $3}'; }

before="$(note_total)"
[[ "$before" == 0 ]] || die "profile $JOPLIN_PROFILE already has $before notes; import needs an empty profile"
expected="$(python3 "$ROOT/scripts/count_enex_notes.py" "${files[@]}")"
echo "==> importing $expected notes from ${#files[@]} notebook file(s) as $fmt"
wait_for_server

restart_hint="Nothing was synced. Delete $JOPLIN_PROFILE, run make joplin-configure, then make import."
failed=()
for f in "${files[@]}"; do
    echo "==> $(basename "$f")"
    joplin import --format enex --output-format "$fmt" -f "$f" || failed+=("$f")
done
(( ${#failed[@]} == 0 )) || die "import failed for: ${failed[*]}
$restart_hint"

actual="$(note_total)"
[[ "$actual" == "$expected" ]] || die "ENEX files contain $expected notes but Joplin has $actual.
$restart_hint"

{ date -Is; printf '%s\n' "${files[@]}"; } > "$IMPORT_MARKER"
echo "==> verified $actual/$expected notes; syncing to ${APP_BASE_URL%/}"
joplin sync
echo "Imported ${#files[@]} notebook(s), $actual notes, and synced."
