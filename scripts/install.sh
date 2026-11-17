#!/usr/bin/env bash
# Forwarding shim: redirects to top-level install.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/../install.sh" "$@"
