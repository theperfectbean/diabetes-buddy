#!/bin/bash
#
# Monthly Knowledge Base Update Script
#
# This script performs automated updates of the diabetes-buddy knowledge base:
#   1. Updates community documentation (OpenAPS, AndroidAPS, Loop)
#   2. Fetches new PubMed research papers
#   3. Updates vector database
#   4. Generates reports
#   5. Commits cache updates to the repository
#
# Crontab setup (1st of month at 2am):
#   0 2 1 * * /path/to/diabetes-buddy/scripts/monthly_knowledge_update.sh
#
# Manual run:
#   ./scripts/monthly_knowledge_update.sh
#   ./scripts/monthly_knowledge_update.sh --dry-run
#

set -e  # Exit on error

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/monthly_update_$(date +%Y%m%d_%H%M%S).log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Parse arguments
DRY_RUN=false
NOTIFY=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --notify)
            NOTIFY=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--notify] [--verbose]"
            exit 1
            ;;
    esac
done

# =============================================================================
# Logging Functions
# =============================================================================

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] ERROR: $1" | tee -a "$LOG_FILE" >&2
}

log_section() {
    echo "" | tee -a "$LOG_FILE"
    echo "============================================================" | tee -a "$LOG_FILE"
    echo "$1" | tee -a "$LOG_FILE"
    echo "============================================================" | tee -a "$LOG_FILE"
}

# =============================================================================
# Environment Setup
# =============================================================================

setup_environment() {
    log_section "Setting up environment"

    cd "$PROJECT_ROOT"
    log "Working directory: $PROJECT_ROOT"

    # Check for Python virtual environment
    if [ -d ".venv" ]; then
        log "Activating virtual environment"
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        log "Activating virtual environment"
        source venv/bin/activate
    else
        log "No virtual environment found, using system Python"
    fi

    # Verify Python is available
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found"
        exit 1
    fi

    log "Python: $(python3 --version)"

    # Load environment variables if .env exists
    if [ -f ".env" ]; then
        log "Loading environment from .env"
        set -a
        source .env
        set +a
    fi
}

# =============================================================================
# Backup Functions
# =============================================================================

create_backup() {
    log_section "Creating backup"

    local backup_dir="$PROJECT_ROOT/data/archive/backup_$(date +%Y%m%d_%H%M%S)"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would create backup at $backup_dir"
        return 0
    fi

    mkdir -p "$backup_dir"

    # Backup version cache
    if [ -f "$PROJECT_ROOT/data/cache/repo_versions.json" ]; then
        cp "$PROJECT_ROOT/data/cache/repo_versions.json" "$backup_dir/"
        log "Backed up repo_versions.json"
    fi

    # Backup file metadata
    if [ -f "$PROJECT_ROOT/data/cache/openaps_file_metadata.json" ]; then
        cp "$PROJECT_ROOT/data/cache/openaps_file_metadata.json" "$backup_dir/"
        log "Backed up openaps_file_metadata.json"
    fi

    # Backup PubMed processed files
    if [ -f "$PROJECT_ROOT/data/cache/pubmed_processed.json" ]; then
        cp "$PROJECT_ROOT/data/cache/pubmed_processed.json" "$backup_dir/"
        log "Backed up pubmed_processed.json"
    fi

    log "Backup created at $backup_dir"
    echo "$backup_dir"
}

# =============================================================================
# Update Functions
# =============================================================================

update_community_docs() {
    log_section "Updating Community Documentation"

    local cmd="python3 scripts/ingest_openaps_docs.py --update"

    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --verbose"
    fi

    if [ "$NOTIFY" = true ]; then
        cmd="$cmd --notify"
    fi

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would run: $cmd"
        # Show what would change
        python3 scripts/ingest_openaps_docs.py --diff 2>&1 | tee -a "$LOG_FILE"
        return 0
    fi

    log "Running: $cmd"

    if $cmd 2>&1 | tee -a "$LOG_FILE"; then
        log "Community docs update completed successfully"
        return 0
    else
        log_error "Community docs update failed"
        return 1
    fi
}

update_pubmed_research() {
    log_section "Updating PubMed Research Papers"

    # Check if PubMed ingestion script exists
    if [ ! -f "$PROJECT_ROOT/agents/pubmed_ingestion.py" ]; then
        log "PubMed ingestion script not found, skipping"
        return 0
    fi

    local cmd="python3 agents/pubmed_ingestion.py --days 30"

    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --verbose"
    fi

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would run: $cmd"
        return 0
    fi

    log "Running: $cmd"

    if $cmd 2>&1 | tee -a "$LOG_FILE"; then
        log "PubMed update completed successfully"
        return 0
    else
        log_error "PubMed update failed (non-critical)"
        return 0  # Don't fail the whole script for PubMed errors
    fi
}

trigger_reindex() {
    log_section "Triggering ChromaDB Reindex"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would trigger reindex"
        return 0
    fi

    # Run the PubMed script with reindex flag if available
    if [ -f "$PROJECT_ROOT/agents/pubmed_ingestion.py" ]; then
        python3 agents/pubmed_ingestion.py --update-index-only --reindex 2>&1 | tee -a "$LOG_FILE"
    fi

    log "Reindex completed"
}

# =============================================================================
# Report Generation
# =============================================================================

generate_report() {
    log_section "Generating Update Report"

    local report_file="$LOG_DIR/monthly_report_$(date +%Y%m%d).md"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would generate report at $report_file"
        return 0
    fi

    cat > "$report_file" << EOF
# Monthly Knowledge Base Update Report

**Date:** $(date '+%Y-%m-%d %H:%M:%S')

## Summary

This report summarizes the monthly knowledge base update.

## Community Documentation

$(python3 scripts/ingest_openaps_docs.py --status 2>/dev/null || echo "Status unavailable")

## Recent Changes

See \`docs/community-knowledge/CHANGELOG.md\` for detailed changes.

## Logs

Full logs available at: \`$LOG_FILE\`

---
*Generated automatically by monthly_knowledge_update.sh*
EOF

    log "Report generated at $report_file"
}

# =============================================================================
# Git Operations
# =============================================================================

commit_cache_updates() {
    log_section "Committing Cache Updates"

    cd "$PROJECT_ROOT"

    # Check if there are changes to commit
    if ! git diff --quiet data/cache/ 2>/dev/null; then
        if [ "$DRY_RUN" = true ]; then
            log "[DRY RUN] Would commit cache updates"
            git diff --stat data/cache/
            return 0
        fi

        log "Committing cache file updates"

        git add data/cache/repo_versions.json 2>/dev/null || true
        git add data/cache/openaps_file_metadata.json 2>/dev/null || true
        git add data/cache/pubmed_processed.json 2>/dev/null || true
        git add data/cache/pmc_processed.json 2>/dev/null || true
        git add docs/community-knowledge/CHANGELOG.md 2>/dev/null || true

        if git diff --cached --quiet; then
            log "No staged changes to commit"
        else
            git commit -m "chore: Monthly knowledge base cache update $(date +%Y-%m-%d)

- Updated repository version cache
- Updated file metadata
- Updated processed articles index

[automated commit]"

            log "Cache updates committed"
        fi
    else
        log "No cache changes to commit"
    fi
}

# =============================================================================
# Cleanup
# =============================================================================

cleanup_old_backups() {
    log_section "Cleaning Up Old Backups"

    local archive_dir="$PROJECT_ROOT/data/archive"

    if [ ! -d "$archive_dir" ]; then
        log "No archive directory found"
        return 0
    fi

    # Count backups
    local backup_count=$(find "$archive_dir" -maxdepth 1 -type d -name "backup_*" | wc -l)
    log "Found $backup_count backups"

    # Keep only last 5 backups
    if [ "$backup_count" -gt 5 ]; then
        local to_delete=$((backup_count - 5))

        if [ "$DRY_RUN" = true ]; then
            log "[DRY RUN] Would delete $to_delete old backups"
            return 0
        fi

        find "$archive_dir" -maxdepth 1 -type d -name "backup_*" | \
            sort | head -n "$to_delete" | \
            while read dir; do
                log "Removing old backup: $dir"
                rm -rf "$dir"
            done

        log "Deleted $to_delete old backups"
    fi

    # Clean old log files (keep last 30 days)
    find "$LOG_DIR" -name "monthly_update_*.log" -mtime +30 -delete 2>/dev/null || true
    find "$LOG_DIR" -name "monthly_report_*.md" -mtime +30 -delete 2>/dev/null || true

    log "Cleanup completed"
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log_section "Starting Monthly Knowledge Base Update"
    log "Arguments: dry_run=$DRY_RUN, notify=$NOTIFY, verbose=$VERBOSE"

    local start_time=$(date +%s)
    local exit_code=0

    # Setup
    setup_environment

    # Create backup
    create_backup

    # Run updates
    if ! update_community_docs; then
        log_error "Community docs update had errors"
        exit_code=1
    fi

    if ! update_pubmed_research; then
        log_error "PubMed update had errors"
        # Don't set exit_code, PubMed is non-critical
    fi

    # Trigger reindex
    trigger_reindex

    # Generate report
    generate_report

    # Commit updates
    commit_cache_updates

    # Cleanup
    cleanup_old_backups

    # Summary
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log_section "Update Complete"
    log "Duration: ${duration} seconds"
    log "Exit code: $exit_code"
    log "Log file: $LOG_FILE"

    return $exit_code
}

# Run main function
main
