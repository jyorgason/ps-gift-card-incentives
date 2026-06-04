#!/usr/bin/env bash
# Refreshes gc_data.json and pushes to GitHub.
# Scheduled hourly by ~/Library/LaunchAgents/com.bamboohr.ps-gift-card-incentives.plist

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/Library/Logs/ps-gift-card-incentives.log"
PYTHON="$(which python3)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== Starting refresh ==="
cd "$REPO_DIR"

# Pull latest in case data was updated elsewhere
git pull --quiet --ff-only origin main || log "WARN: git pull skipped"

# Generate data
log "Running generate_data.py..."
"$PYTHON" "$REPO_DIR/scripts/generate_data.py" 2>&1 | tee -a "$LOG"

# Commit and push if data changed
if git diff --quiet data/gc_data.json; then
  log "No data changes — nothing to push."
else
  git add data/gc_data.json
  git commit -m "chore: refresh gc_data.json [$(date '+%Y-%m-%dT%H:%M:%SZ')]"
  git push origin main
  log "Pushed updated gc_data.json to GitHub."
fi

log "=== Done ==="
