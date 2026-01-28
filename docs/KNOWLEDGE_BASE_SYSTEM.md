# Autonomous Knowledge Base Management System

## Overview

The Diabetes Buddy Autonomous Knowledge Base Management System automatically fetches, maintains, and updates clinical guidelines and device manuals without user intervention. After a one-time device selection during onboarding, the system operates completely autonomously.

## Architecture

### Components

1. **Device Registry** (`config/device_registry.json`)
   - Comprehensive catalog of insulin pumps, CGMs, and clinical guidelines
   - Contains fetch metadata, URLs, and update schedules
   - Easily extensible for new devices

2. **Knowledge Fetcher** (`agents/knowledge_fetcher.py`)
   - Autonomous agent that downloads and manages knowledge sources
   - Supports multiple fetch methods:
     - Direct PDF downloads
     - Web page scraping with CSS selectors
     - Git repository cloning (for OpenAPS docs)
   - Implements retry logic and rate limiting
   - Maintains version history with rollback capability

3. **Background Scheduler** (`scripts/schedule_updates.py`)
   - Runs automatic update checks on configurable schedule (default: weekly)
   - Silent operation with notifications only for important updates
   - Configurable via user preferences

4. **Researcher Integration** (`agents/researcher.py`)
   - Dynamically discovers available knowledge sources
   - Uses latest versions automatically
   - Includes version info in all responses
   - Provides staleness warnings for outdated sources

5. **Web Interface**
   - Onboarding wizard (`/setup`) for initial device selection
   - Knowledge base status widget on dashboard
   - Manual update check button
   - Notification system for important updates

## User Flow

### Initial Setup (One-Time)

1. User visits `/setup` on first launch
2. Selects their insulin pump from dropdown (e.g., "CamAPS FX")
3. Selects their CGM from dropdown (e.g., "Libre 3")
4. Clicks "Start Setup"
5. System fetches 5 sources in 30-60 seconds:
   - ADA Standards of Care 2026
   - NHS T1D Guidelines
   - OpenAPS Documentation
   - User's pump manual
   - User's CGM manual
6. Knowledge base ready!

### Ongoing Operation (Autonomous)

1. **Weekly Update Checks** (Monday 3 AM by default)
   - System checks all sources for new versions
   - Downloads updates automatically if available
   - Maintains last 2 versions for rollback
   - Logs all activity

2. **Smart Notifications**
   - Clinical guideline updates → User notified
   - Device manual updates → Silent (unless configured otherwise)
   - Errors → Logged, system continues with cached version

3. **Zero Maintenance Required**
   - User never thinks about knowledge base again
   - Always has current information
   - Evidence-based answers with proper citations

## File Structure

```
config/
  device_registry.json          # Master device catalog
  user_profile.json             # User's selected devices and preferences

docs/
  knowledge-sources/            # All fetched sources
    pump/
      camaps_fx/
        v1.0/
          camaps_fx.pdf
          metadata.json
        v1.1/
          camaps_fx.pdf
          metadata.json
        latest -> v1.1          # Symlink to current version
    cgm/
      libre_3/
        v2.0/
          libre_3.pdf
          metadata.json
        latest -> v2.0
    guideline/
      ada_standards/
        2026/
          ada_standards.pdf
          metadata.json
        latest -> 2026
      openaps_docs/
        latest/
          .git/
          docs/
          metadata.json

data/
  notifications.json            # Update notifications for user

logs/
  knowledge_updates.log         # All update activity
```

## API Endpoints

### GET `/api/knowledge/registry`
Returns device registry for setup UI.

**Response:**
```json
{
  "pumps": {
    "camaps_fx": {
      "id": "camaps_fx",
      "name": "CamAPS FX",
      "manufacturer": "CamDiab"
    }
  },
  "cgms": { ... }
}
```

### POST `/api/knowledge/setup`
Initial device setup and knowledge base creation.

**Request:**
```json
{
  "pump_id": "camaps_fx",
  "cgm_id": "libre_3"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Knowledge base setup completed. 5 sources fetched successfully.",
  "results": {
    "guideline_ada_standards": {
      "success": true,
      "file_path": "...",
      "version": "2026"
    },
    ...
  }
}
```

### GET `/api/knowledge/status`
Get current status of all knowledge sources.

**Response:**
```json
{
  "sources": [
    {
      "type": "guideline",
      "id": "ada_standards",
      "name": "ADA Standards of Care",
      "version": "2026",
      "last_updated": "2026-01-15T...",
      "days_old": 13,
      "status": "current"
    }
  ],
  "last_check": "2026-01-28T...",
  "auto_update_enabled": true
}
```

### POST `/api/knowledge/check-updates`
Manually trigger update check.

**Response:**
```json
{
  "success": true,
  "updates_found": 2,
  "details": { ... }
}
```

### POST `/api/knowledge/update-device`
Change pump or CGM.

**Request:**
```json
{
  "device_type": "pump",
  "device_id": "tandem_tslim_x2"
}
```

### GET `/api/knowledge/notifications`
Get recent update notifications.

## Configuration

### User Profile (`config/user_profile.json`)

```json
{
  "version": "1.0.0",
  "devices": {
    "pump": "camaps_fx",
    "cgm": "libre_3"
  },
  "knowledge_sources": [
    {
      "type": "guideline",
      "id": "ada_standards",
      "added_at": "2026-01-28T...",
      "version": "2026"
    }
  ],
  "auto_update_enabled": true,
  "update_preferences": {
    "notify_on_guideline_changes": true,
    "notify_on_device_updates": false,
    "update_frequency_days": 7
  }
}
```

### Device Registry Entry Example

```json
{
  "camaps_fx": {
    "name": "CamAPS FX",
    "manufacturer": "CamDiab",
    "manual_url": "https://camdiab.com/resources/",
    "fetch_method": "scrape",
    "selectors": {
      "manual_link": "a[href*='manual']"
    },
    "version_pattern": "v(\\d+\\.\\d+)",
    "file_prefix": "camaps_fx_manual",
    "update_frequency_days": 90,
    "license": "Freely available from manufacturer"
  }
}
```

## Fetch Methods

### 1. Direct Download
For stable PDF URLs that don't change.

```json
{
  "fetch_method": "direct",
  "direct_pdf_url": "https://example.com/manual.pdf"
}
```

### 2. Web Scraping
For dynamic pages where PDF link must be found.

```json
{
  "fetch_method": "scrape",
  "manual_url": "https://example.com/manuals/",
  "selectors": {
    "pdf_link": "a[href*='.pdf']"
  }
}
```

### 3. Git Clone
For documentation in git repositories.

```json
{
  "fetch_method": "git",
  "git_repo": "https://github.com/openaps/docs.git"
}
```

## Update Detection

The system uses multiple methods to detect updates:

1. **Content Hashing**: SHA256 hash comparison
2. **Version Parsing**: Regex patterns to extract version numbers
3. **Last-Modified Headers**: HTTP header comparison
4. **Git Commits**: Commit hash comparison for repos
5. **Time-Based**: Configurable check frequency per source

## Error Handling

### Network Failures
- 3 retry attempts with exponential backoff
- Continue with cached version if download fails
- Log error for admin review

### Website Changes
- Fallback from CSS selector to generic PDF search
- Alert user if scraping fails completely
- Provide manual download instructions

### Version Conflicts
- Always keep last 2 versions
- Automatic rollback on parse failures
- Metadata tracks all version changes

## Running the Scheduler

### As a Daemon (Background Service)

```bash
# Start scheduler in daemon mode
python scripts/schedule_updates.py --mode daemon

# Or run once and exit
python scripts/schedule_updates.py --check-now
```

### As a Systemd Service (Linux)

Create `/etc/systemd/system/diabuddy-updates.service`:

```ini
[Unit]
Description=Diabetes Buddy Knowledge Base Update Scheduler
After=network.target

[Service]
Type=simple
User=gary
WorkingDirectory=/home/gary/diabetes-buddy
ExecStart=/home/gary/diabetes-buddy/.venv/bin/python scripts/schedule_updates.py --mode daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable diabuddy-updates
sudo systemctl start diabuddy-updates
sudo systemctl status diabuddy-updates
```

### As a Cron Job

```bash
# Check for updates daily at 3 AM
0 3 * * * cd /home/gary/diabetes-buddy && .venv/bin/python scripts/schedule_updates.py --check-now >> logs/cron.log 2>&1
```

## Testing

Run the comprehensive test suite:

```bash
# All tests
pytest tests/test_knowledge_base.py -v

# Specific test categories
pytest tests/test_knowledge_base.py::TestKnowledgeFetcher -v
pytest tests/test_knowledge_base.py::TestResearcherIntegration -v

# With coverage
pytest tests/test_knowledge_base.py --cov=agents --cov-report=html
```

## CLI Usage

The knowledge fetcher can be used from command line:

```bash
# Initial setup
python agents/knowledge_fetcher.py setup camaps_fx libre_3

# Check for updates
python agents/knowledge_fetcher.py check-updates

# View status
python agents/knowledge_fetcher.py status
```

## Adding New Devices

To add support for a new device:

1. **Find the manual URL** from manufacturer website

2. **Determine fetch method**:
   - Can you directly link to PDF? → Use `direct`
   - Must scrape page for link? → Use `scrape`
   - Documentation in git repo? → Use `git`

3. **Add to device_registry.json**:

```json
{
  "insulin_pumps": {
    "new_pump_id": {
      "name": "New Pump Name",
      "manufacturer": "Manufacturer Name",
      "manual_url": "https://...",
      "fetch_method": "direct",
      "direct_pdf_url": "https://.../manual.pdf",
      "version_pattern": "v(\\d+\\.\\d+)",
      "file_prefix": "new_pump_manual",
      "update_frequency_days": 180,
      "license": "Freely available from manufacturer"
    }
  }
}
```

4. **Test the fetch**:

```bash
python -c "
from agents.knowledge_fetcher import KnowledgeFetcher
f = KnowledgeFetcher()
result = f.fetch_source('pump', 'new_pump_id')
print(result)
"
```

## Legal Compliance

All fetched content includes:

- **Source Attribution**: Manufacturer name and URL
- **Access Date**: When content was fetched
- **License Info**: Usage rights and restrictions
- **Disclaimer**: Educational use only

Example metadata:
```json
{
  "source_name": "CamAPS FX User Manual",
  "manufacturer": "CamDiab",
  "source_url": "https://...",
  "fetched_at": "2026-01-28T10:30:00",
  "license": "Freely available from manufacturer",
  "content_hash": "abc123...",
  "notes": "User manual for educational purposes"
}
```

## Troubleshooting

### No sources fetched during setup
- Check internet connection
- Verify manufacturer websites are accessible
- Review logs: `logs/knowledge_updates.log`

### Update checks failing
- Check rate limiting (default: 2 second delay between requests)
- Verify User-Agent is not blocked
- Test individual sources with CLI

### Sources marked as outdated
- Check `update_frequency_days` in registry
- Manually trigger update: click "Check Now" in UI
- Verify source is still available online

### Scraping not finding PDFs
- Website may have changed structure
- Update CSS selectors in registry
- Switch to `direct` method if stable URL available

## Performance

- **Initial Setup**: 30-60 seconds for 5 sources
- **Update Check**: 10-20 seconds (only checks, doesn't re-download)
- **Background Impact**: Minimal (runs once per week at 3 AM)
- **Storage**: ~50MB for typical setup (5 sources × 2 versions)

## Security

- **No Credentials Required**: All sources are publicly available
- **Rate Limiting**: Respects manufacturer server limits
- **User-Agent**: Identifies as educational tool
- **Robots.txt**: Checked before scraping
- **HTTPS Only**: All downloads over secure connections

## Future Enhancements

Potential improvements for future versions:

1. **Multi-Language Support**: Fetch manuals in user's language
2. **Differential Updates**: Only download changed pages
3. **OCR Integration**: Extract text from image-based PDFs
4. **Smart Summarization**: Auto-generate manual summaries
5. **Community Registry**: User-contributed device sources
6. **Version Comparison**: Highlight changes between versions
7. **Mobile App**: Push notifications for important updates

## Support

For issues or questions:

1. Check logs: `logs/knowledge_updates.log`
2. Run diagnostics: `python agents/knowledge_fetcher.py status`
3. Review test suite: `pytest tests/test_knowledge_base.py -v`
4. File issue with logs and configuration

---

**System Status**: Production Ready ✅

Last Updated: January 28, 2026
