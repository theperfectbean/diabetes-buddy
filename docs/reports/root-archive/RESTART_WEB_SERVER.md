# Web Server Restart Required

**Date:** February 3, 2026  
**Reason:** Updated device-aware prompts require web server restart

---

## Changes Made

Enhanced both `_build_prompt()` and `_build_hybrid_prompt()` in `agents/unified_agent.py` to require:
- Specific instructions from device manual (e.g., "tap Boost tab, set duration to 2-4 hours")
- Actionable HOW-TO steps, not just feature mentions
- Duration recommendations and specific numbers from the manual

---

## Current Status

**CLI Testing:** ✅ Working correctly with device-specific guidance

**Web App:** ⚠️ Still showing old generic response (needs restart)

---

## Web Server Restart Commands

The following processes are running and need restart:

```bash
# Stop all web servers
sudo pkill -f gunicorn
sudo pkill -f uvicorn

# Then restart your web server
# (use whatever command you normally use to start it)
```

---

## Validation After Restart

**Test Query:** "how do i mitigate highs?"

**Expected Response Should Include:**
- ✅ "Your CamAPS FX" (6+ mentions)
- ✅ "Boost" feature with HOW to use it ("tap Boost tab")
- ✅ Duration guidance ("2-4 hours", "over 9 hours")
- ✅ "Personal glucose target" with HOW to set it ("tap the green '+' icon")
- ✅ Specific thresholds ("16.7 mmol/L", "0.2 mmol/L/min")

**Should NOT Include:**
- ❌ "basal adjustments" (manual pump advice)
- ❌ "overnight basal"
- ❌ "pre-bolus timing" (generic advice)
- ❌ "carb counting accuracy" (generic advice)

---

## CLI Test Command

To verify the fix is working in CLI:

```bash
cd ~/diabetes-buddy
source venv/bin/activate
python -c "
from agents.unified_agent import UnifiedAgent
agent = UnifiedAgent()
response = agent.process('how do i mitigate highs?')
print(response.answer)
"
```

**Current CLI Output:** Device-specific ✅

**Current Web Output:** Generic ❌ (pre-restart)

---

## What Changed

### Before (Generic Response):
- Mentioned "basal adjustments"
- Suggested "pre-bolus timing"
- Generic diabetes advice

### After (Device-Specific Response):
- Explains how to activate Boost ("tap the Boost tab")
- Includes duration recommendations ("initially try 2-4 hours")
- Mentions specific settings ("tap the green '+' icon")
- References alert thresholds ("16.7 mmol/L")
- All advice is CamAPS FX-specific

---

## Summary

The code changes are complete and tested via CLI. The web server is serving stale code from before the prompt enhancements. Restart the web server to apply the new device-aware prompts.
