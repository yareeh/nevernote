#!/usr/bin/env bash
# Run the pinned Joplin CLI against this instance's profile (per ENV_FILE).
source "$(dirname "$0")/lib.sh"
load_env
joplin "$@"
