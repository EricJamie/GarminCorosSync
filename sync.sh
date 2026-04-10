#!/bin/bash
# Garmin ⇄ Coros Sync - Linux/Mac runner script
#
# Usage:
#   ./sync.sh                        # Full bidirectional sync
#   ./sync.sh --garmin-only          # Only Garmin → Coros
#   ./sync.sh --coros-only           # Only Coros → Garmin
#   ./sync.sh --dry-run              # Preview without uploading
#
# Environment variables (from .env or shell):
#   COROS_EMAIL, COROS_PASSWORD, GARMIN_TOKEN_DIR

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"

# Load .env if exists
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Run sync with all arguments passed through
# Log to file with timestamp
LOG_FILE="${LOG_DIR}/sync_$(date '+%Y%m%d_%H%M%S').log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting sync..." | tee -a "${LOG_FILE}"
python "${SCRIPT_DIR}/sync.py" "$@" 2>&1 | tee -a "${LOG_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sync finished" | tee -a "${LOG_FILE}"
