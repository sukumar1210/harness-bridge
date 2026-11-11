#!/usr/bin/env bash
set -euo pipefail

REPO="sukumar1210/harness-bridge"
INSTALL_DIR="${HOME}/.harness-bridge"
VENV_DIR="${INSTALL_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"

echo "=== Installing Harness Bridge ==="

# Ensure Python 3.11+
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not installed." >&2
    exit 1
fi

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment in ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

echo "Fetching latest release information from GitHub..."
RELEASE_JSON=$(curl -sSL "https://api.github.com/repos/${REPO}/releases/latest" || true)
WHEEL_URL=$(echo "${RELEASE_JSON}" | grep -o 'https://[^"]*harness_bridge[^"]*\.whl' | head -n 1 || true)

if [ -n "${WHEEL_URL}" ]; then
    echo "Downloading wheel from ${WHEEL_URL}..."
    TMP_WHL=$(mktemp --suffix=.whl)
    curl -sSL "${WHEEL_URL}" -o "${TMP_WHL}"
    "${VENV_DIR}/bin/pip" install --upgrade --quiet "${TMP_WHL}"
    rm -f "${TMP_WHL}"
else
    echo "Installing latest package from repository..."
    "${VENV_DIR}/bin/pip" install --upgrade --quiet "git+https://github.com/${REPO}.git"
fi

ln -sf "${VENV_DIR}/bin/harness-bridge" "${BIN_DIR}/harness-bridge"

echo "=== Harness Bridge installed successfully to ${BIN_DIR}/harness-bridge ==="
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo "Note: Please ensure ${BIN_DIR} is in your PATH (e.g. export PATH=\"\$HOME/.local/bin:\$PATH\")."
fi
