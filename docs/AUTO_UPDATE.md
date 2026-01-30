# Diabetes Buddy Auto-Update System

This document describes the automatic knowledge base update system for Diabetes Buddy.

## Overview

The auto-update system keeps the knowledge base current by:
1. **OpenAPS Documentation**: Pulls updates from OpenAPS, AndroidAPS, and Loop documentation repos
2. **PubMed Research**: Searches for new diabetes research articles
3. **ChromaDB**: Incrementally updates vector embeddings for new/changed content

## Quick Start

### Manual Update
```bash
# Run full update
python scripts/monthly_update.py

# Dry run (see what would change)
python scripts/monthly_update.py --dry-run

# Update only OpenAPS docs
python scripts/monthly_update.py --openaps-only

# Update only PubMed
python scripts/monthly_update.py --pubmed-only

# Check storage usage
python scripts/monthly_update.py --estimate
```

### First-Time Setup
```bash
# Clone OpenAPS repositories
python scripts/ingest_openaps_docs.py --clone

# Process all files
python scripts/ingest_openaps_docs.py --force

# Fetch PubMed articles
python agents/pubmed_ingestion.py --days 365 --fetch-full-text
```

## Automatic Updates with systemd

### Installation

1. Copy the service files:
```bash
sudo cp scripts/diabetes-buddy-update.timer /etc/systemd/system/
sudo cp scripts/diabetes-buddy-update.service /etc/systemd/system/
```

2. Reload systemd and enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable diabetes-buddy-update.timer
sudo systemctl start diabetes-buddy-update.timer
```

3. Verify:
```bash
systemctl status diabetes-buddy-update.timer
systemctl list-timers
```

### Configuration

Edit `/etc/systemd/system/diabetes-buddy-update.timer` to change the schedule:

```ini
# Monthly (1st of each month at 3 AM)
OnCalendar=*-*-01 03:00:00

# Weekly (every Monday at 3 AM)
OnCalendar=Mon *-*-* 03:00:00

# Daily at midnight
OnCalendar=*-*-* 00:00:00
```

### Manual Trigger
```bash
# Run the update now
sudo systemctl start diabetes-buddy-update.service

# Check logs
journalctl -u diabetes-buddy-update.service -f
```

## Update Process

### Phase 1: OpenAPS Documentation

1. **Git Fetch**: Checks for new commits in each repo
2. **Change Detection**: Uses `git diff` to find modified files only
3. **Incremental Processing**: Only re-parses changed `.md` and `.rst` files
4. **Embedding Update**: Removes old embeddings, creates new ones

Repositories:
- `data/sources/openaps/` - OpenAPS core documentation
- `data/sources/androidaps/` - AndroidAPS user guide
- `data/sources/loop/` - Loop documentation

### Phase 2: PubMed Research

1. **Incremental Search**: Only searches for articles since last run
2. **Filtering**: English, abstract required, open access preferred
3. **Full-text Fetch**: Downloads PMC full-text XML when available
4. **Relevance Scoring**: Weights articles by T1D relevance keywords

Search terms:
- "type 1 diabetes" AND ("management" OR "insulin" OR "continuous glucose monitoring")
- Hybrid closed loop systems
- Automated insulin delivery
- CGM accuracy

### Phase 3: Changelog Generation

Each update creates a log at `data/update_logs/YYYY-MM-DD_changelog.md` containing:
- Summary of changes per phase
- Storage statistics
- ChromaDB collection counts
- Any errors encountered

## Monitoring

### Log Files

| Log | Location |
|-----|----------|
| Monthly update | `logs/monthly_update.log` |
| OpenAPS ingestion | `logs/knowledge_updates.log` |
| PubMed ingestion | `logs/pubmed_ingestion.log` |
| Scheduler | `logs/schedule_updates.log` |

### Update Logs
```bash
# List recent changelogs
ls -la data/update_logs/

# View latest
cat data/update_logs/$(ls -t data/update_logs/ | head -1)
```

### Storage Check
```bash
python scripts/monthly_update.py --estimate
```

Example output:
```
STORAGE ESTIMATE
====================
Git Repositories:
  openaps: 45.23 MB
  androidaps: 128.67 MB
  loop: 67.89 MB

ChromaDB:
  Database: 234.56 MB

  Collections:
    openaps_docs: 4521 chunks
    pubmed_research: 892 chunks
    theory: 394 chunks
    ...

  Total chunks: 6234

TOTAL: 476.35 MB
```

## ChromaDB Collections

| Collection | Source | Confidence |
|------------|--------|------------|
| `openaps_docs` | OpenAPS/AndroidAPS/Loop repos | 0.8 |
| `pubmed_research` | PubMed/PMC articles | 0.7 |
| `theory` | Think Like a Pancreas | 1.0 |
| `camaps` | CamAPS FX Manual | 1.0 |
| `ypsomed` | Ypsomed Pump Manual | 1.0 |
| `libre` | FreeStyle Libre 3 Manual | 1.0 |
| `ada_standards` | ADA Standards 2026 | 1.0 |
| `australian_guidelines` | Australian Diabetes Guidelines | 0.9 |

## Troubleshooting

### Update fails with git error
```bash
# Check repository status
cd data/sources/openaps && git status

# Reset if corrupted
rm -rf data/sources/openaps
python scripts/ingest_openaps_docs.py --clone
```

### PubMed rate limiting
The system respects NCBI rate limits (3 req/s without API key, 10 req/s with key).
Set `PUBMED_API_KEY` in `.env` for faster updates.

### ChromaDB corruption
```bash
# Backup and rebuild
mv .cache/chromadb .cache/chromadb.bak
python scripts/ingest_openaps_docs.py --force
python agents/pubmed_ingestion.py --reindex
```

### Memory issues
The systemd service limits memory to 2GB. For large updates:
```bash
# Edit the service
sudo systemctl edit diabetes-buddy-update.service

# Add/modify:
[Service]
MemoryMax=4G
```

## Security Notes

- The update service runs as user `gary`, not root
- Network access is required for git fetch and PubMed API
- `.env` file with API keys is read but not exposed
- systemd sandboxing limits file system access

## Related Scripts

| Script | Purpose |
|--------|---------|
| `scripts/monthly_update.py` | Main orchestrator |
| `scripts/ingest_openaps_docs.py` | OpenAPS doc management |
| `scripts/schedule_updates.py` | Legacy scheduler (Python-based) |
| `agents/pubmed_ingestion.py` | PubMed article fetching |
| `scripts/full_foundation_setup.py` | Complete setup orchestrator |
