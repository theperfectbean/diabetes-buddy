#!/bin/bash
#
# Weekly PubMed Research Ingestion Script for Diabetes Buddy
#
# This script is designed to be run via cron to automatically ingest
# new research papers from PubMed into the knowledge base.
#
# Installation:
#   1. Make executable: chmod +x scripts/weekly_pubmed_update.sh
#   2. Add to crontab (run `crontab -e`):
#      # Run every Monday at 4:00 AM
#      0 4 * * 1 /path/to/diabetes-buddy/scripts/weekly_pubmed_update.sh
#
# Environment Variables:
#   PUBMED_API_KEY    - Optional: NCBI API key for higher rate limits
#   DIABETES_BUDDY_DIR - Optional: Override project directory
#
# Logs are written to: logs/pubmed_ingestion.log
#

set -e

# Determine script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${DIABETES_BUDDY_DIR:-$(dirname "$SCRIPT_DIR")}"

# Change to project directory
cd "$PROJECT_ROOT"

# Log file
LOG_FILE="$PROJECT_ROOT/logs/pubmed_cron.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting weekly PubMed ingestion"
log "Project root: $PROJECT_ROOT"

# Check for virtual environment
VENV_PATHS=(
    "$PROJECT_ROOT/.venv"
    "$PROJECT_ROOT/venv"
    "$PROJECT_ROOT/.env"
)

VENV_ACTIVATED=false
for VENV in "${VENV_PATHS[@]}"; do
    if [ -f "$VENV/bin/activate" ]; then
        log "Activating virtual environment: $VENV"
        source "$VENV/bin/activate"
        VENV_ACTIVATED=true
        break
    fi
done

if [ "$VENV_ACTIVATED" = false ]; then
    log "WARNING: No virtual environment found, using system Python"
fi

# Verify Python and required modules
if ! python3 -c "import aiohttp" 2>/dev/null; then
    log "ERROR: Required Python module 'aiohttp' not found"
    log "Run: pip install aiohttp"
    exit 1
fi

# Check for API key (optional but recommended)
if [ -n "$PUBMED_API_KEY" ]; then
    log "Using NCBI API key (10 requests/sec rate limit)"
else
    log "No API key set (3 requests/sec rate limit)"
    log "Set PUBMED_API_KEY for faster ingestion"
fi

# Run the ingestion pipeline
log "Running PubMed ingestion pipeline..."

# Default: 7 days back, 50 results per term
DAYS_BACK=${PUBMED_DAYS_BACK:-7}
MAX_RESULTS=${PUBMED_MAX_RESULTS:-50}

INGESTION_START=$(date +%s)

if python3 "$PROJECT_ROOT/agents/pubmed_ingestion.py" \
    --days "$DAYS_BACK" \
    --limit "$MAX_RESULTS" \
    --reindex \
    2>&1 | tee -a "$LOG_FILE"; then

    INGESTION_END=$(date +%s)
    DURATION=$((INGESTION_END - INGESTION_START))
    log "Ingestion completed successfully in ${DURATION}s"
else
    INGESTION_END=$(date +%s)
    DURATION=$((INGESTION_END - INGESTION_START))
    log "ERROR: Ingestion failed after ${DURATION}s"
    exit 1
fi

# Update the master index
log "Updating master index..."
python3 "$PROJECT_ROOT/agents/pubmed_ingestion.py" --update-index-only 2>&1 | tee -a "$LOG_FILE"

# Generate summary notification
ARTICLES_ADDED=$(grep -oP 'Total articles added:\s+\K\d+' "$LOG_FILE" 2>/dev/null | tail -1 || echo "0")
ARTICLES_FOUND=$(grep -oP 'Total articles found:\s+\K\d+' "$LOG_FILE" 2>/dev/null | tail -1 || echo "0")

# Save notification for web interface
NOTIFICATIONS_FILE="$PROJECT_ROOT/data/notifications.json"
mkdir -p "$(dirname "$NOTIFICATIONS_FILE")"

if [ -f "$NOTIFICATIONS_FILE" ]; then
    # Append to existing notifications
    python3 -c "
import json
from datetime import datetime

with open('$NOTIFICATIONS_FILE', 'r') as f:
    data = json.load(f)

data['notifications'] = data.get('notifications', [])[-49:]  # Keep last 50
data['notifications'].append({
    'type': 'pubmed_update',
    'timestamp': datetime.now().isoformat(),
    'message': 'PubMed ingestion: $ARTICLES_ADDED new articles added ($ARTICLES_FOUND found)',
    'read': False
})

with open('$NOTIFICATIONS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
else
    # Create new notifications file
    python3 -c "
import json
from datetime import datetime

data = {
    'notifications': [{
        'type': 'pubmed_update',
        'timestamp': datetime.now().isoformat(),
        'message': 'PubMed ingestion: $ARTICLES_ADDED new articles added ($ARTICLES_FOUND found)',
        'read': False
    }]
}

with open('$NOTIFICATIONS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
fi

log "Notification saved"
log "Weekly PubMed ingestion complete"
log "=========================================="

# Clean up old logs (keep last 30 days)
find "$PROJECT_ROOT/logs" -name "pubmed_*.log" -mtime +30 -delete 2>/dev/null || true

exit 0
