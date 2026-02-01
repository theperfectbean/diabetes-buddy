# OpenAPS Community Documentation Ingestion

This document describes the automated system for ingesting and maintaining community documentation from OpenAPS, AndroidAPS, and Loop projects.

## Overview

The ingestion system provides:
- **Git-based version tracking**: Detects changes between runs using commit hashes
- **Selective re-indexing**: Only processes changed files, not the entire corpus
- **ChromaDB integration**: Creates vector embeddings for semantic search
- **Automated scheduling**: Monthly updates via cron
- **Safety features**: Backups, rollback, and archive management

## Repositories Tracked

| Repository | URL | Branch | Files |
|------------|-----|--------|-------|
| OpenAPS | https://github.com/openaps/docs | master | ~60 |
| AndroidAPS | https://github.com/openaps/AndroidAPSdocs | master | ~3000 |
| Loop | https://github.com/LoopKit/loopdocs | main | ~110 |

## Directory Structure

```
diabetes-buddy/
├── docs/community-knowledge/
│   ├── raw-repos/           # Cloned git repositories
│   │   ├── openaps/
│   │   ├── androidaps/
│   │   └── loop/
│   └── CHANGELOG.md         # Auto-generated update log
├── data/
│   ├── cache/
│   │   ├── repo_versions.json       # Commit hash cache
│   │   └── openaps_file_metadata.json  # Per-file metadata
│   └── archive/
│       └── chromadb_backup_*/       # Vector DB backups
├── logs/
│   └── knowledge_updates.log        # Update logs
└── scripts/
    ├── ingest_openaps_docs.py       # Main ingestion script
    └── monthly_knowledge_update.sh  # Automation script
```

## CLI Commands

### First-Time Setup

```bash
# Clone all repositories
python scripts/ingest_openaps_docs.py --clone
```

This will:
1. Clone all three repositories to `docs/community-knowledge/raw-repos/`
2. Store initial commit hashes in `data/cache/repo_versions.json`

### Check for Updates

```bash
# Check and process updates
python scripts/ingest_openaps_docs.py --update

# With notification
python scripts/ingest_openaps_docs.py --update --notify

# Verbose output
python scripts/ingest_openaps_docs.py --update --verbose
```

This will:
1. Fetch latest changes from remote
2. Compare HEAD with cached commit hash
3. If changed:
   - List modified/new/deleted `.md` files via `git diff`
   - Process only changed files
   - Update embeddings in ChromaDB (delete old, add new)
   - Update changelog
   - Update commit hash in cache
4. If unchanged: Log "No updates" and exit

### Preview Changes

```bash
# Show what would change without updating
python scripts/ingest_openaps_docs.py --diff
```

Example output:
```
============================================================
Repository Status
============================================================

OpenAPS Documentation (openaps)
----------------------------------------
  Status: UPDATES AVAILABLE
  Current: 30b2443b -> New: a1b2c3d4
  Changed files: 3

  Changes:
    [M] docs/troubleshooting/dawn-phenomenon.md
    [+] docs/guides/exercise-with-camaps.md
    [-] docs/deprecated/old-guide.md
```

### Force Re-Process

```bash
# Re-process all files (useful after schema changes)
python scripts/ingest_openaps_docs.py --force
```

This will:
1. Create a backup of ChromaDB
2. Process ALL markdown files in all repositories
3. Regenerate all embeddings (if API key available)
4. Update all metadata

### Check Status

```bash
python scripts/ingest_openaps_docs.py --status
```

Example output:
```
============================================================
OpenAPS Documentation Status
============================================================

Repository Versions:
  OpenAPS Documentation
    Commit: 30b2443b
    Updated: 2026-01-30T10:58:21
  AndroidAPS Documentation
    Commit: 8bad2971
    Updated: 2026-01-30T10:59:04
  Loop Documentation
    Commit: c23a3d75
    Updated: 2026-01-30T10:59:22

File Metadata:
  OpenAPS Documentation: 62 files tracked
  AndroidAPS Documentation: 2979 files tracked
  Loop Documentation: 110 files tracked

ChromaDB Collection: community_docs
  Total documents: 15432
```

## Automated Scheduling

### Monthly Update Script

```bash
# Run manually
./scripts/monthly_knowledge_update.sh

# Dry run (preview what would happen)
./scripts/monthly_knowledge_update.sh --dry-run

# With notifications
./scripts/monthly_knowledge_update.sh --notify
```

### Crontab Setup

Add to crontab (`crontab -e`):

```cron
# Monthly knowledge base update (1st of month at 2am)
0 2 1 * * /path/to/diabetes-buddy/scripts/monthly_knowledge_update.sh >> /path/to/diabetes-buddy/logs/cron.log 2>&1
```

### What the Monthly Script Does

1. **Environment setup**: Activates virtual environment, loads `.env`
2. **Backup**: Creates backup of cache files
3. **Community docs update**: Runs `ingest_openaps_docs.py --update`
4. **PubMed update**: Runs `pubmed_ingestion.py --days 30`
5. **ChromaDB reindex**: Triggers vector DB reindexing
6. **Report generation**: Creates monthly report in `logs/`
7. **Git commit**: Commits cache updates to repository
8. **Cleanup**: Removes old backups (keeps last 5)

## Metadata Tracking

Each processed file has metadata stored in `data/cache/openaps_file_metadata.json`:

```json
{
  "openaps/docs/troubleshooting/dawn-phenomenon.md": {
    "file": "docs/troubleshooting/dawn-phenomenon.md",
    "source_repo": "openaps",
    "commit_hash": "a1b2c3d4",
    "last_updated": "2026-01-15T08:30:00",
    "commit_message": "Updated dawn phenomenon strategies",
    "word_count": 1523,
    "processed_at": "2026-01-30T02:00:00",
    "content_hash": "md5hash..."
  }
}
```

## Changelog Generation

Updates are logged to `docs/community-knowledge/CHANGELOG.md`:

```markdown
## 2026-01-30 Update - OpenAPS Documentation

### Modified Files
- **docs/troubleshooting/dawn-phenomenon.md**
  - Commit: "Updated dawn phenomenon strategies for hybrid closed-loop"

### New Files
- **docs/guides/exercise-with-camaps.md**
  - Commit: "Added CamAPS-specific exercise guidance"

---
```

## ChromaDB Integration

### Collection: `community_docs`

Documents are chunked and embedded with metadata:
- `file_key`: Unique identifier (repo/path)
- `source_repo`: Repository name
- `file_path`: Path within repository
- `commit_hash`: Git commit hash
- `source_type`: "community_docs"

### Embedding Requirements

For embeddings to work, you need:
1. `GEMINI_API_KEY` environment variable set
2. Or another LLM provider configured via `LLM_PROVIDER`

If no API key is available, files are still processed and metadata tracked - embeddings are simply skipped.

## Safety Features

### Backup & Rollback

Before any update:
1. ChromaDB is backed up to `data/archive/chromadb_backup_YYYYMMDD_HHMMSS/`
2. If processing fails, automatic rollback occurs

### Archive Management

- Backups older than 5 versions are automatically deleted
- Log files older than 30 days are cleaned up

## Troubleshooting

### "Repository not cloned"

Run the clone command first:
```bash
python scripts/ingest_openaps_docs.py --clone
```

### "Failed to initialize LLM provider"

This is a warning, not an error. Files are still processed; only embeddings are skipped. To enable embeddings:
```bash
export GEMINI_API_KEY="your-api-key"
```

### "Could not connect to tenant default_tenant"

ChromaDB initialization issue. Try:
```bash
rm -rf .cache/chromadb
python scripts/ingest_openaps_docs.py --force
```

### Large number of files to process

AndroidAPS has ~3000 files. Initial processing takes a few minutes. Subsequent updates only process changed files.

## Integration with Diabetes Buddy

The community documentation is searchable via the ChromaDB researcher agent:

```python
from agents.researcher_chromadb import ResearcherAgent

researcher = ResearcherAgent()
# Search community docs via the community_docs collection
```

## Notifications

When `--notify` is used:
1. Summary logged to `logs/knowledge_updates.log`
2. Notification saved to `data/notifications.json` (for web UI)
3. Email notification (if configured - see future implementation)

## Future Enhancements

- [ ] Email notifications via SMTP
- [ ] Slack/Discord webhook integration
- [ ] Web UI for manual updates
- [ ] Differential embedding (only re-embed changed chunks)
- [ ] Support for additional community repos (Tidepool, Nightscout)
