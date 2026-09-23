#!/usr/bin/env bash
# Point the repo-local Joplin CLI profile at Joplin Server.
source "$(dirname "$0")/lib.sh"
load_env
require_env APP_BASE_URL JOPLIN_USER_EMAIL JOPLIN_USER_PASSWORD
mkdir -p "$JOPLIN_PROFILE"
joplin config sync.target 9 >/dev/null                      # 9 = Joplin Server
joplin config sync.9.path "${APP_BASE_URL%/}" >/dev/null
joplin config sync.9.username "$JOPLIN_USER_EMAIL" >/dev/null
joplin config sync.9.password "$JOPLIN_USER_PASSWORD" >/dev/null
echo "Joplin CLI profile $JOPLIN_PROFILE -> ${APP_BASE_URL%/} as $JOPLIN_USER_EMAIL"
