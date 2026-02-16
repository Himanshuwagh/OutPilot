#!/bin/bash
#
# Install the cold outreach pipeline as a macOS launchd service.
# Runs daily at 6 AM. Survives reboots.
#
# Usage:
#   bash install_service.sh          # Install
#   bash install_service.sh uninstall # Uninstall
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.coldoutreach.daily"
PLIST_SRC="${SCRIPT_DIR}/${PLIST_NAME}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs"

# --- Uninstall ---
if [ "${1}" = "uninstall" ]; then
    echo "Uninstalling ${PLIST_NAME}..."
    launchctl unload "${PLIST_DST}" 2>/dev/null || true
    rm -f "${PLIST_DST}"
    echo "Done. Service removed."
    exit 0
fi

# --- Install ---
echo "Installing cold outreach pipeline as a daily launchd service..."
echo "Project directory: ${SCRIPT_DIR}"

# Ensure LaunchAgents directory exists
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "${LOG_DIR}"

# Generate plist with actual paths
sed \
    -e "s|__PROJECT_DIR__|${SCRIPT_DIR}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "${PLIST_SRC}" > "${PLIST_DST}"

# Find the python3 path
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "ERROR: python3 not found in PATH."
    exit 1
fi

# Replace /usr/bin/env python3 with actual python path in the plist
# This ensures launchd finds the right python even without shell init
sed -i '' "s|/usr/bin/env</string>|${PYTHON_PATH}</string>|g" "${PLIST_DST}"
# Remove the separate python3 argument since we merged it into the path
sed -i '' '/<string>python3<\/string>/d' "${PLIST_DST}"

# Load the service
launchctl unload "${PLIST_DST}" 2>/dev/null || true
launchctl load "${PLIST_DST}"

echo ""
echo "Service installed successfully!"
echo ""
echo "  Plist: ${PLIST_DST}"
echo "  Logs:  ${LOG_DIR}/cold-outreach.log"
echo "  Errors: ${LOG_DIR}/cold-outreach-error.log"
echo ""
echo "The pipeline will run daily at 6:00 AM."
echo "If your Mac is asleep at 6 AM, it will run when you wake it."
echo ""
echo "Commands:"
echo "  Trigger now:  launchctl start ${PLIST_NAME}"
echo "  Check status: launchctl list | grep coldoutreach"
echo "  View logs:    tail -f ${LOG_DIR}/cold-outreach.log"
echo "  Uninstall:    bash ${SCRIPT_DIR}/install_service.sh uninstall"
