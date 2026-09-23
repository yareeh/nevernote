#!/usr/bin/env bash
# Rotate the default admin password and create/activate your user.
source "$(dirname "$0")/lib.sh"
load_env
require_env APP_BASE_URL JOPLIN_ADMIN_PASSWORD JOPLIN_USER_EMAIL JOPLIN_USER_PASSWORD
wait_for_server
exec python3 "$ROOT/scripts/server_user.py"
