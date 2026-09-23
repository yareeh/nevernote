#!/usr/bin/env bash
# Create an env file from .env.example with random strong passwords.
# Usage: scripts/init-env.sh <env-file> [KEY=VALUE ...]   (overrides/additions)
# Refuses to overwrite an existing file.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:?usage: init-env.sh <env-file> [KEY=VALUE ...]}"
shift
[[ -e "$out" ]] && { echo "$out already exists; not overwriting" >&2; exit 1; }

python3 - "$ROOT/.env.example" "$out" "$@" <<'EOF'
import os, re, secrets, sys

template, out, *overrides = sys.argv[1:]
values = {
    "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
    "JOPLIN_ADMIN_PASSWORD": secrets.token_urlsafe(18),
    "JOPLIN_USER_PASSWORD": secrets.token_urlsafe(18),
}
for kv in overrides:
    k, _, v = kv.partition("=")
    values[k] = v
# Quote values so the file is valid for both `source` (bash) and Compose.
values = {k: f'"{v}"' if re.search(r"[^\w@.:/+-]", v) else v for k, v in values.items()}

lines = []
for line in open(template):
    m = re.match(r"^([A-Z_]+)=", line)
    if m and m.group(1) in values:
        line = f"{m.group(1)}={values.pop(m.group(1))}\n"
    lines.append(line)
if values:
    lines.append("\n# Instance-specific settings\n")
    lines += [f"{k}={v}\n" for k, v in values.items()]

fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as f:
    f.writelines(lines)
EOF
echo "Wrote $out (mode 600) with generated passwords."
