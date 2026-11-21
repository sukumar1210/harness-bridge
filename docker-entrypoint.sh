#!/bin/sh
set -e

# ------------------------------------------------------------------------------
# Harness Bridge Smart Entrypoint
# ------------------------------------------------------------------------------

# 1. Auto-discover host CLI tools (e.g. agy, custom scripts) from mounted /home
for user_bin in /home/*/.local/bin; do
    if [ -d "$user_bin" ]; then
        case ":$PATH:" in
            *":$user_bin:"*) ;;
            *) export PATH="$user_bin:$PATH" ;;
        esac
    fi
done

# 2. Auto-align HOME and session persistence with host user if mounted
if [ -z "${HARNESS_BRIDGE_STORAGE_DIR:-}" ]; then
    for user_home in /home/*; do
        if [ -d "$user_home/.local" ] || [ -d "$user_home/.harness-bridge" ]; then
            export HOME="$user_home"
            export HARNESS_BRIDGE_STORAGE_DIR="$user_home/.harness-bridge/sessions"
            break
        fi
    done
fi

# Ensure storage directory exists and is writable
if [ -n "${HARNESS_BRIDGE_STORAGE_DIR:-}" ]; then
    mkdir -p "$HARNESS_BRIDGE_STORAGE_DIR" 2>/dev/null || true
fi

# 3. Ensure git safe.directory covers all mounted volumes across all UIDs
git config --system --add safe.directory '*' 2>/dev/null || true

# 4. Dispatch CLI command or fall back to native execution
if [ $# -eq 0 ]; then
    exec harness-bridge serve --transport unified --host 0.0.0.0 --port 8000
fi

case "$1" in
    serve|list|version|run|test|setup|reload|update|-*)
        exec harness-bridge "$@"
        ;;
    *)
        if command -v "$1" >/dev/null 2>&1; then
            exec "$@"
        else
            exec harness-bridge "$@"
        fi
        ;;
esac
