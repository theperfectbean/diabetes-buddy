# Safety Filter Fix - February 3, 2026

## Problem
Query "how do i mitigate my highs?" was being blocked by the safety filter with tier 4 (dangerous) classification in the web app.

## Root Causes Found

### 1. False Positive: "stop your insulin"
**Issue**: Pattern `\b(skip|stop|discontinue)\s+(your\s+)?(insulin|medication|meds)\b` was matching educational text like "it can stop your insulin delivery" (describing a malfunction) as if it were telling users to stop their insulin.

**Fix**: Updated DANGEROUS_PATTERNS to distinguish between imperative instructions and descriptive statements:
```python
# Before
r"\b(skip|stop|discontinue)\s+(your\s+)?(insulin|medication|meds)\b"

# After  
r"\b(skip|stop|discontinue)\s+(your\s+|taking\s+)?(insulin|medication|meds)\b(?!\s+(delivery|if|when|because))"
```

Added negative lookahead `(?!\s+(delivery|if|when|because))` to prevent matching "stop insulin delivery" or conditional statements.

### 2. False Positive: "100 U/ml" insulin concentration
**Issue**: Pattern `\b(\d+(?:\.\d+)?)\s*(u|units?)\b` was matching "100 U/ml" in educational text about insulin specifications, treating it as dosing advice.

**Fix**: Already had logic to skip units check for educational queries via `is_educational_query` flag, but the query wasn't being recognized as educational.

### 3. Query Not Recognized as Educational
**Issue**: "how do i mitigate my highs?" wasn't matching EDUCATIONAL_STRATEGY_PATTERNS because "mitigate" wasn't in the verb list.

**Fix**: Added "mitigate" to the educational patterns:
```python
r"\bways?\s+to\s+(improve|reduce|fix|address|manage|handle|mitigate)\b",
r"\bhow\s+(can|do|should)\s+I\s+(improve|reduce|fix|address|manage|handle|mitigate)\b",
```

## Changes Made

**File**: `agents/safety_tiers.py`

1. Updated DANGEROUS_PATTERNS (lines 48-51):
   - Made pattern more specific to imperative instructions
   - Added negative lookahead to exclude "stop insulin delivery" and conditional contexts
   - Added explicit pattern for "don't take" instructions

2. Updated EDUCATIONAL_STRATEGY_PATTERNS (lines 69-71):
   - Added "mitigate" to the list of management verbs

## Testing

### Test Cases Validated
✓ Educational context: "it can stop your insulin delivery" → ALLOWED
✓ Dangerous advice: "You should stop your insulin" → BLOCKED  
✓ Dangerous advice: "skip your insulin doses" → BLOCKED
✓ Dangerous advice: "don't take your insulin" → BLOCKED
✓ Query classification: "how do i mitigate my highs?" → EDUCATIONAL (tier_1_education)

### Web App Testing
- Query now returns detailed educational response with strategies for managing high glucose
- Response includes monitoring advice, pump troubleshooting, lifestyle factors, medication info
- Safety tier: TIER_1 (educational) with ALLOW action
- No false positive blocking

## Deployment

Changes deployed via Docker container restart:
```bash
sudo docker restart diabetes-buddy
```

Container mounts `/home/gary/diabetes-buddy/agents` as volume, so changes were immediately available after reload.

## Next Steps

1. **Device-Aware Responses**: The response is still generic (mentions "insulin pump" but not "CamAPS FX"). This is because the web app uses `triage_agent.process()` instead of `unified_agent` which has the enhanced device-aware prompts. Consider updating web app to use unified_agent or porting device-aware prompts to triage_agent.

2. **Additional Educational Verbs**: Consider adding more verbs to EDUCATIONAL_STRATEGY_PATTERNS:
   - "deal with", "cope with", "prevent", "avoid", "correct", "treat"

3. **Pattern Refinement**: Monitor for other false positives. The current patterns are more precise but may still catch edge cases.

## Files Modified
- `agents/safety_tiers.py`: Updated DANGEROUS_PATTERNS and EDUCATIONAL_STRATEGY_PATTERNS
- `web/app.py`: Added debug logging (can be removed after validation)

## Test Files Created
- `test_safety_query.py`: Tests query classification  
- `test_safety_response.py`: Tests full response classification
- `test_dangerous_pattern.py`: Tests DANGEROUS_PATTERNS
- `test_safety_patterns.py`: Comprehensive pattern test suite
- `test_units_pattern.py`: Tests UNITS_PATTERN matching
- `test_web_query.py`: Tests web API endpoint

These test files can be kept for regression testing.
