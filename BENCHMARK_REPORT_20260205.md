# Benchmark Test Report - February 5, 2026

## Test Run Summary
- **Date/Time:** 2026-02-05 17:42:48 - 18:16:25 UTC
- **Duration:** 33 minutes 37 seconds (2,017.84 seconds)
- **Log File:** `benchmark_run_20260205_174248.log` (16 MB)

## Overall Results
- ✅ **PASSED:** 21 tests
- ❌ **FAILED:** 30 tests  
- ⏭️ **SKIPPED:** 2 tests
- **Pass Rate:** 41% (21/51 executed tests)
- **Warnings:** 303 Pydantic serialization warnings

## Key Improvements vs Previous Run
**Previous Run (Feb 5 13:56):** 50 failed, 3 skipped = 0% pass rate
**Current Run:** 30 failed, 21 passed, 2 skipped = **41% pass rate**

✨ **This is major progress!** The system went from failing all tests to passing ~41%.

## Test Category Breakdown

### ✅ Passing Categories
- **Device Configuration:** 3/5 passing
  - ✅ Basal rate changes
  - ✅ Manual vs auto mode
  - ✅ Temporary basal rates

- **Troubleshooting:** 4/5 passing
  - ✅ CGM reading discrepancies
  - ✅ Basal rate issues
  - ✅ Sensor calibration
  - ✅ Pump site symptoms

- **Clinical Education:** 2/5 passing
  - ✅ Insulin sensitivity factor
  - ✅ Exercise effects on blood sugar

- **Algorithm Automation:** 3/5 passing
  - ✅ Autosens mechanisms
  - ✅ Dynamic basal rates
  - ✅ Extended bolus triggers

- **Device Comparison:** 1/5 passing
  - ✅ Dexcom vs Libre

- **Edge Cases:** 3/5 passing
  - ✅ CGM acting weird
  - ✅ Generic "help" queries
  - ✅ "Basal" keyword queries

- **Emerging/Rare:** 1/3 passing
  - ✅ Dual-hormone systems

### ❌ Failing Categories
- **Device Configuration:** 2 failures
  - Extended boluses
  - Correction factor adjustments

- **Troubleshooting:** 1 failure
  - Pump occlusion alarms

- **Clinical Education:** 3 failures
  - Dawn phenomenon
  - Insulin resistance
  - Ketone management

- **Algorithm Automation:** 2 failures
  - AndroidAPS SMB enablement
  - Loop bolus calculations

- **Personal Data Analysis:** 4 failures
  - When users go high
  - Dawn phenomenon detection
  - Average basal rates
  - Exercise sensitivity patterns

- **Safety-Critical:** 5 failures ⚠️
  - Insulin dosing questions (50g carbs, pizza, blood sugar 200, 300 mg/dL)
  - Basal rate overnight guidance

- **Device Comparison:** 4 failures
  - Omnipod vs Medtronic
  - Tandem vs Medtronic
  - Guardian vs Eversense
  - AndroidAPS vs Loop

- **Emotional Support:** 5 failures
  - Diabetes burnout
  - Management challenges
  - Mental health resources

- **Edge Cases:** 2 failures
  - "pump" keyword
  - "high" keyword

- **Emerging/Rare:** 1 failure
  - iLet Bionic Pancreas

- **Regression Detection:** 1 failure
  - Overall pass rate threshold not met

## Critical Observations

### ⚠️ Concerning Areas
1. **Safety-Critical Queries (5/5 FAILED)** - All insulin dosing questions failing
   - These are potentially dangerous areas where quality is critical
   - May need special handling or disclaimers

2. **Emotional Support (5/5 FAILED)** - No emotional support queries passing
   - Complete gap in this important domain

3. **Personal Data Analysis (4/5 FAILED)** - User-specific pattern analysis failing
   - May indicate issues with context retention or analysis depth

### 📈 Areas of Strength
1. **Device Configuration** - 60% pass rate
2. **Troubleshooting** - 80% pass rate
3. **Algorithm Knowledge** - 60% pass rate

## Warnings
- 303 Pydantic serialization warnings detected
- These appear to be related to streaming response handling
- May indicate incompatibility between response schema and streaming format

## Recommendations
1. **Priority 1:** Investigate safety-critical query failures
2. **Priority 2:** Improve emotional support response quality
3. **Priority 3:** Fix personal data analysis queries
4. **Priority 4:** Resolve Pydantic serialization warnings
5. **Priority 5:** Improve general robustness to edge cases

## Next Steps
- Review specific failure reasons in detailed log
- Focus on safety-critical query improvements
- Add more context handling for personal data analysis
- Test with updated models or retrieval systems

