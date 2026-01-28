# Knowledge Base Quick Start Guide

## For End Users

### First Time Setup (5 minutes)

1. **Start the web interface**:
   ```bash
   cd /home/gary/diabetes-buddy
   source .venv/bin/activate
   python web/app.py
   ```

2. **Open your browser** to `http://localhost:8000/setup`

3. **Select your devices**:
   - Choose your insulin pump from dropdown
   - Choose your CGM from dropdown
   - Click "Start Setup"

4. **Wait 30-60 seconds** while the system fetches:
   - Clinical guidelines (ADA, NHS, OpenAPS)
   - Your pump manual
   - Your CGM manual

5. **Done!** Knowledge base is ready. Go to dashboard and start asking questions.

### That's It!

The system now:
- ✅ Automatically checks for updates weekly
- ✅ Downloads new versions when available
- ✅ Provides evidence-based answers with citations
- ✅ Warns you about outdated information
- ✅ Requires **zero maintenance** from you

## For Administrators

### Initial Installation

1. **Install dependencies**:
   ```bash
   pip install beautifulsoup4 requests schedule
   ```

2. **Verify installation**:
   ```bash
   python agents/knowledge_fetcher.py status
   ```

### Running the Scheduler

**Option 1: Systemd Service (Recommended for production)**

```bash
# Create service file
sudo nano /etc/systemd/system/diabuddy-updates.service

# Add content (see KNOWLEDGE_BASE_SYSTEM.md)

# Enable and start
sudo systemctl enable diabuddy-updates
sudo systemctl start diabuddy-updates
```

**Option 2: Cron Job (Simple)**

```bash
# Edit crontab
crontab -e

# Add line:
0 3 * * * cd /home/gary/diabetes-buddy && .venv/bin/python scripts/schedule_updates.py --check-now
```

**Option 3: Manual (Testing)**

```bash
# Run once now
python scripts/schedule_updates.py --check-now

# Run in background
nohup python scripts/schedule_updates.py --mode daemon > logs/scheduler.log 2>&1 &
```

### Monitoring

**Check scheduler status**:
```bash
# Systemd
sudo systemctl status diabuddy-updates

# Cron
tail -f logs/knowledge_updates.log

# Process
ps aux | grep schedule_updates
```

**View logs**:
```bash
# Update activity
tail -f logs/knowledge_updates.log

# Last 50 lines
tail -50 logs/knowledge_updates.log

# Errors only
grep ERROR logs/knowledge_updates.log
```

### Testing

**Test a single source fetch**:
```bash
python -c "
from agents.knowledge_fetcher import KnowledgeFetcher
f = KnowledgeFetcher()
result = f.fetch_source('guideline', 'ada_standards')
print('Success!' if result['success'] else 'Failed')
"
```

**Run full test suite**:
```bash
pytest tests/test_knowledge_base.py -v
```

**Test update detection**:
```bash
python agents/knowledge_fetcher.py check-updates
```

## Common Tasks

### Change Devices

**Via Web UI**: Click "Settings" → "Knowledge Base" → "Change Device"

**Via CLI**:
```bash
python -c "
from agents.knowledge_fetcher import KnowledgeFetcher
f = KnowledgeFetcher()
result = f.update_device('pump', 'tandem_tslim_x2')
print(result)
"
```

### Force Update Check

**Via Web UI**: Click "Check Now" in Knowledge Base Status widget

**Via CLI**:
```bash
python scripts/schedule_updates.py --check-now
```

### View Current Status

**Via Web UI**: Dashboard → Knowledge Base Status widget

**Via CLI**:
```bash
python agents/knowledge_fetcher.py status
```

### Add a New Device

1. Edit `config/device_registry.json`
2. Add new entry (see KNOWLEDGE_BASE_SYSTEM.md for format)
3. Test fetch:
   ```bash
   python agents/knowledge_fetcher.py setup new_pump_id test_cgm
   ```

## Troubleshooting

### "Setup Required" message persists

**Solution**: Run initial setup
```bash
python agents/knowledge_fetcher.py setup camaps_fx libre_3
```

### Sources showing as "outdated"

**Solution**: Manually check for updates
```bash
python scripts/schedule_updates.py --check-now
```

### Fetch failing for specific source

**Solution**: Check logs and test individually
```bash
# View errors
grep "ERROR.*camaps_fx" logs/knowledge_updates.log

# Test specific source
python -c "
from agents.knowledge_fetcher import KnowledgeFetcher
f = KnowledgeFetcher()
try:
    result = f.fetch_source('pump', 'camaps_fx')
    print('Success:', result)
except Exception as e:
    print('Error:', e)
"
```

### Scheduler not running

**Check if running**:
```bash
# Systemd
sudo systemctl status diabuddy-updates

# Process
ps aux | grep schedule_updates
```

**Restart**:
```bash
# Systemd
sudo systemctl restart diabuddy-updates

# Manual
pkill -f schedule_updates
nohup python scripts/schedule_updates.py --mode daemon &
```

## Performance Tips

### Reduce Update Frequency

Edit `config/user_profile.json`:
```json
{
  "update_preferences": {
    "update_frequency_days": 30
  }
}
```

### Disable Auto-Updates

```json
{
  "auto_update_enabled": false
}
```

Then manually check when needed via UI or CLI.

### Limit Sources

Only fetch what you need. Remove unused sources from `knowledge_sources` array in user profile.

## Security Best Practices

1. **Run as non-root user** (recommended: dedicated service account)
2. **Restrict file permissions**:
   ```bash
   chmod 600 config/user_profile.json
   chmod 755 docs/knowledge-sources
   ```
3. **Monitor logs** for suspicious activity
4. **Keep dependencies updated**:
   ```bash
   pip install --upgrade beautifulsoup4 requests schedule
   ```

## Getting Help

1. **Check documentation**: `docs/KNOWLEDGE_BASE_SYSTEM.md`
2. **Review logs**: `logs/knowledge_updates.log`
3. **Run diagnostics**: `python agents/knowledge_fetcher.py status`
4. **Test suite**: `pytest tests/test_knowledge_base.py -v`

## Success Metrics

Your knowledge base is healthy if:

✅ All sources show status "current" or "stale" (not "outdated" or "error")  
✅ Last check timestamp is within last 7 days  
✅ Scheduler is running (check with `systemctl status` or `ps`)  
✅ Logs show no recurring errors  
✅ User can ask questions and receive cited answers  

## Quick Reference

| Task | Command |
|------|---------|
| Setup | `python agents/knowledge_fetcher.py setup <pump> <cgm>` |
| Check updates | `python scripts/schedule_updates.py --check-now` |
| View status | `python agents/knowledge_fetcher.py status` |
| View logs | `tail -f logs/knowledge_updates.log` |
| Run tests | `pytest tests/test_knowledge_base.py -v` |
| Start scheduler | `python scripts/schedule_updates.py --mode daemon` |
| Check scheduler | `systemctl status diabuddy-updates` |

---

**Need more details?** See [KNOWLEDGE_BASE_SYSTEM.md](KNOWLEDGE_BASE_SYSTEM.md)

**Ready to start?** Visit `http://localhost:8000/setup` in your browser!
