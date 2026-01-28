# Glooko Data Integration Guide

> **IMPORTANT SAFETY DISCLAIMER**
>
> This tool is for **EDUCATIONAL PURPOSES ONLY** and does NOT provide medical advice.
>
> - **NEVER** adjust insulin doses based solely on this analysis
> - **ALWAYS** discuss findings with your healthcare team before making changes
> - Patterns shown are observational and require clinical interpretation
> - If you experience severe hypoglycemia or hyperglycemia, contact your healthcare provider immediately
>
> *Data analysis for educational purposes. Discuss findings with your healthcare team.*

---

## 1. Overview

The Glooko Integration Module analyzes your diabetes data exports to:

- **Calculate glucose metrics** - Time in range, variability, estimated A1C
- **Detect patterns** - Dawn phenomenon, post-meal spikes, insulin sensitivity variations
- **Generate research questions** - Personalized queries based on your data
- **Route to knowledge sources** - Connect findings to Think Like a Pancreas, CamAPS FX, and Ypsomed manuals

### What Gets Analyzed

| Data Type | Source | Analysis |
|-----------|--------|----------|
| CGM Readings | Libre 3 via CamAPS | Time in range, variability, trends |
| Insulin Delivery | Ypsomed pump | Bolus patterns, basal rates |
| Carbohydrates | Bolus wizard entries | Post-meal spike correlation |
| Exercise | Manual entries | Impact on glucose levels |

### Key Features

- **Automatic unit conversion** - Handles both mmol/L and mg/dL
- **Pattern detection** - Identifies dawn phenomenon, post-meal spikes
- **Smart caching** - Avoids reprocessing unchanged files
- **Safety integration** - All outputs pass through SafetyAuditor

---

## 2. Quick Start

### Step 1: Export Your Data from Glooko

1. Log in to [my.glooko.com](https://my.glooko.com)
2. Go to **Settings** → **Export Data**
3. Select your date range (recommend 14-30 days)
4. Click **Export** and download the ZIP file

### Step 2: Save to Data Directory

```bash
# Move your export to the data directory
mv ~/Downloads/export_*.zip data/glooko/
```

### Step 3: Run the Analysis

```bash
# Full analysis with colored output
python scripts/analyze_and_advise.py

# Or use the test script for detailed debugging
python scripts/test_analyzer.py --verbose
```

### Step 4: Review Your Results

The script displays:

```
======================================================================
 DIABETES BUDDY - PERSONALIZED ANALYSIS REPORT
======================================================================

  Analysis Period: 2026-01-14 to 2026-01-27 (14 days)

  Glucose Metrics:
    Time in Range (70-180):  66.8% [BELOW TARGET]
    Time Below 70:            0.4% [OK]
    Variability (CV):        29.7% [STABLE]

  Detected Patterns:
    1. Dawn Phenomenon [Confidence: 57%]
    2. Post-Meal Spikes [Frequency: 84%]

  Research Questions:
    [1] What does Think Like a Pancreas say about meal bolus timing?
    [2] How can I use Ypsomed's extended bolus feature?
    ...
```

---

## 3. Export Instructions

### From Glooko Web Portal

1. **Navigate to my.glooko.com**
   - Sign in with your Glooko credentials
   - Ensure your devices are synced (CamAPS, Libre 3)

2. **Access Export Settings**
   - Click the gear icon (⚙️) in the top right
   - Select "Export Data" from the menu

3. **Configure Export Options**
   - **Date Range**: Select 14-30 days for best pattern detection
   - **Format**: Choose "CSV" (default)
   - **Include**: Ensure all data types are checked:
     - ☑️ CGM/BGM readings
     - ☑️ Insulin data
     - ☑️ Food/Carbs
     - ☑️ Exercise
     - ☑️ Notes

4. **Download**
   - Click "Generate Export"
   - Download the ZIP file (named like `export_Your Name.zip`)

### From Glooko Mobile App

1. Open the Glooko app
2. Tap **Menu** → **Settings** → **Export Data**
3. Select date range and tap **Export**
4. Choose "Save to Files" and save to a location you can access

### Supported File Formats

| Format | Support | Notes |
|--------|---------|-------|
| ZIP archive | ✅ Full | Preferred - contains all CSV files |
| Individual CSV | ✅ Full | Auto-detects file type |
| Directory | ✅ Full | Processes all CSVs in folder |

---

## 4. Understanding Your Results

### Time in Range (TIR)

The percentage of time your glucose stays between 70-180 mg/dL.

| TIR % | Status | Color | Interpretation |
|-------|--------|-------|----------------|
| ≥70% | Target Met | 🟢 Green | Excellent control |
| 50-69% | Below Target | 🟡 Yellow | Room for improvement |
| <50% | Needs Attention | 🔴 Red | Discuss with care team |

**Clinical Targets** (per consensus guidelines):
- Time in Range (70-180): >70%
- Time Below 70: <4%
- Time Below 54: <1%
- Time Above 180: <25%
- Time Above 250: <5%

### Dawn Phenomenon

A natural rise in blood glucose between 3am-8am caused by hormonal changes.

| Confidence | Meaning |
|------------|---------|
| >70% | Strong pattern - occurs most mornings |
| 50-70% | Moderate pattern - occurs frequently |
| <50% | Weak/inconsistent pattern |

**What triggers detection:**
- Rising glucose trend during 3am-8am window
- Slope >5 mg/dL per hour
- Pattern present on >50% of analyzed days

**Typical strategies** (discuss with your healthcare team):
- Overnight basal adjustments
- CamAPS Boost mode timing
- Evening snack modifications

### Post-Meal Spikes

Glucose rises occurring 1-3 hours after eating.

| Spike Rate | Interpretation |
|------------|----------------|
| <30% | Normal - most meals well-controlled |
| 30-50% | Moderate - some timing opportunities |
| 50-70% | Elevated - consider pre-bolus timing |
| >70% | High - discuss strategies with care team |

**Spike threshold**: >50 mg/dL rise OR peak >180 mg/dL

**Common causes:**
- Delayed bolus timing
- Carb counting inaccuracies
- High glycemic index foods
- Insufficient insulin-to-carb ratio

### Estimated A1C

Calculated using the ADAG formula:
```
Estimated A1C = (Average Glucose + 46.7) / 28.7
```

**Accuracy notes:**
- Based on CGM average, not lab measurement
- May differ from lab A1C by ±0.5%
- Use as a trend indicator, not a diagnosis
- Always confirm with laboratory testing

### Coefficient of Variation (CV)

Measures glucose variability as a percentage.

| CV % | Stability |
|------|-----------|
| ≤36% | Stable glucose patterns |
| 36-45% | Moderate variability |
| >45% | High variability - increased hypo risk |

---

## 5. Generated Research Questions

### How Questions Are Generated

The system analyzes your patterns and creates targeted questions:

```
Pattern Detected          →  Research Question Generated
─────────────────────────────────────────────────────────
Dawn Phenomenon (57%)     →  "What strategies does Think Like a
                              Pancreas recommend for dawn phenomenon?"

Post-meal spikes (84%)    →  "How can I use the Ypsomed pump's
                              extended bolus feature?"

TIR below target (66.8%)  →  "What are key strategies for
                              improving time in range?"
```

### Question Priority Levels

| Priority | Label | Trigger |
|----------|-------|---------|
| HIGH | 🔴 | Confidence ≥70% or safety concern |
| MEDIUM | 🟡 | Confidence 50-69% |
| LOW | 🔵 | Informational patterns |

### Knowledge Source Routing

Questions are tagged with the most relevant knowledge source:

| Source | Topics |
|--------|--------|
| **Think Like a Pancreas** | Behavioral strategies, dosing theory, lifestyle |
| **CamAPS FX Guide** | Boost/Ease-off modes, algorithm behavior |
| **Ypsomed Manual** | Pump features, extended bolus, hardware |

---

## 6. Integration with Other Agents

### Complete Workflow

```
┌─────────────────┐
│  Glooko Export  │
│   (ZIP file)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GlookoAnalyzer  │  ← Parses data, detects patterns
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ generate_       │  ← Creates targeted questions
│ research_queries│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Triage Agent   │  ← Routes to knowledge sources
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Researcher Agent │  ← Retrieves relevant information
│     (RAG)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Safety Auditor  │  ← Blocks doses, adds disclaimers
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Safe Output   │  ← Educational information only
└─────────────────┘
```

### Programmatic Integration

```python
from agents import GlookoAnalyzer, TriageAgent, SafetyAuditor
from agents.data_ingestion import generate_research_queries

# Analyze data
analyzer = GlookoAnalyzer()
results = analyzer.process_export("data/glooko/export.zip")

# Generate questions
queries = generate_research_queries(results, max_queries=5)

# Route through agents (if configured)
triage = TriageAgent()
safety = SafetyAuditor(triage)

for query in queries:
    response = safety.process(query["question"])
    print(response.response)
```

---

## 7. Privacy & Data Safety

### Local Processing Only

- **No data uploads** - All processing happens on your local machine
- **No cloud storage** - Your health data never leaves your computer
- **No external APIs** - Analysis uses local algorithms only

### Data Directory Protection

The `data/` directory is automatically excluded from version control:

```gitignore
# .gitignore
data/          # All Glooko exports and analysis cache
```

### What's Stored Locally

| Location | Contents | Sensitive? |
|----------|----------|------------|
| `data/glooko/` | Raw export files | ✅ Yes - contains PII |
| `data/cache/` | Processed results (JSON) | ✅ Yes - derived data |
| `data/analysis/` | Custom reports | ✅ Yes - may contain PII |

### Best Practices

1. **Never commit data files** to version control
2. **Use encryption** on your local drive if possible
3. **Delete old exports** after analysis if not needed
4. **Review cache files** periodically for cleanup

### Clearing Cached Data

```bash
# Clear analysis cache
python -m agents.data_ingestion --clear-cache

# Manually remove all data
rm -rf data/glooko/* data/cache/* data/analysis/*
```

---

## 8. Troubleshooting

### Column Name Mismatches

**Symptom:** "Could not determine type for file" warnings

**Cause:** Non-standard column names in export

**Solution:**
```bash
# Run with verbose mode to see column names
python scripts/test_analyzer.py --verbose

# Look for output like:
# DEBUG - CGM columns found: ['Timestamp', 'Unknown Column', ...]
```

The parser supports these column names:
- **CGM**: `Timestamp`, `CGM Glucose Value (mmol/l)`, `Serial Number`
- **Insulin**: `Timestamp`, `Insulin Delivered (U)`, `Insulin Type`
- **Carbs**: `Timestamp`, `Carbs (g)`, `Carbs Input (g)`

### Empty Data Files

**Symptom:** "0 CGM readings" or empty results

**Possible causes:**
1. Export date range has no data
2. Devices not synced to Glooko
3. Wrong file selected

**Solution:**
```bash
# Check file contents
unzip -l data/glooko/export.zip

# Inspect a specific CSV
python -c "
import zipfile
zf = zipfile.ZipFile('data/glooko/export.zip')
with zf.open('cgm_data_1.csv') as f:
    print(f.read().decode()[:500])
"
```

### Date Range Limitations

**Minimum recommended:** 7 days
**Optimal:** 14-30 days

With less than 7 days:
- Dawn phenomenon detection may be unreliable
- Pattern confidence will be lower
- Recommendations less accurate

### Unit Conversion Issues

The system automatically handles mmol/L ↔ mg/dL conversion:
- **Conversion factor:** 18.0182
- **mmol/L columns:** Detected by column names containing "mmol"
- **mg/dL columns:** Default assumption for numeric glucose values

**Verify conversion:**
```bash
# Check if values look correct (should be 70-180 range typically)
python scripts/test_analyzer.py --verbose 2>&1 | grep "Average Glucose"
```

### Cache Issues

**Symptom:** Old results showing after new export

**Solution:**
```bash
# Force fresh analysis
python scripts/analyze_and_advise.py --no-cache

# Or clear cache entirely
rm data/cache/*.json
```

### Import Errors

**Symptom:** `ModuleNotFoundError: No module named 'pandas'`

**Solution:**
```bash
# Install dependencies
pip install -r requirements.txt

# Or install specifically
pip install pandas>=2.0.0 numpy>=1.24.0 scipy>=1.11.0
```

---

## 9. Advanced Usage

### Programmatic API

#### Basic Analysis

```python
from agents import GlookoAnalyzer

analyzer = GlookoAnalyzer(use_cache=True)
results = analyzer.process_export("data/glooko/export.zip")

# Access specific metrics
tir = results["time_in_range"]
print(f"Time in Range: {tir['time_in_range_70_180']}%")
print(f"Average Glucose: {tir['average_glucose']} mg/dL")
print(f"Estimated A1C: {tir['estimated_a1c']}%")
```

#### Pattern Analysis

```python
patterns = results["patterns"]

# Dawn phenomenon
dawn = patterns["dawn_phenomenon"]
if dawn["detected"]:
    print(f"Dawn phenomenon: {dawn['confidence']}% confidence")
    print(f"Average rise: {dawn['average_rise_rate']} mg/dL/hour")

# Post-meal spikes
spikes = patterns["post_meal_spikes"]
print(f"Spike rate: {spikes['spike_rate']}%")
print(f"Average spike: {spikes['average_spike']} mg/dL")
```

#### Custom Query Generation

```python
from agents.data_ingestion import generate_research_queries

# Generate more queries
queries = generate_research_queries(results, max_queries=10)

# Filter by pattern type
dawn_queries = [q for q in queries if q["pattern_type"] == "dawn_phenomenon"]

# Filter by knowledge source
tlap_queries = [q for q in queries if q["knowledge_source"] == "think_like_pancreas"]
```

#### Direct Parser Access

```python
from agents import GlookoParser

parser = GlookoParser()
parsed = parser.load_export("data/glooko/export.zip")

# Access raw data
print(f"CGM readings: {len(parsed.cgm_readings)}")
print(f"Insulin records: {len(parsed.insulin_records)}")
print(f"Carb entries: {len(parsed.carb_records)}")

# Iterate readings
for reading in parsed.cgm_readings[:10]:
    print(f"{reading.timestamp}: {reading.glucose_mg_dl} mg/dL")
```

#### Custom Analysis

```python
from agents import DataAnalyzer, GlookoParser

parser = GlookoParser()
parsed = parser.load_export("data/glooko/export.zip")

analyzer = DataAnalyzer()

# Time in range with custom thresholds
tir = analyzer.calculate_time_in_range(parsed.cgm_readings)

# Dawn phenomenon analysis
dawn = analyzer.detect_dawn_phenomenon(parsed.cgm_readings)

# Post-meal analysis
spikes = analyzer.detect_post_meal_spikes(
    parsed.cgm_readings,
    parsed.carb_records
)

# Exercise correlation
exercise = analyzer.correlate_exercise_impact(
    parsed.cgm_readings,
    parsed.exercise_records
)
```

#### Saving Reports

```bash
# Save to file (no colors)
python scripts/analyze_and_advise.py --output report.txt

# JSON output for programmatic use
python scripts/test_analyzer.py --json > analysis.json
```

#### Integration with Jupyter

```python
# In a Jupyter notebook
from agents import GlookoAnalyzer
import pandas as pd

analyzer = GlookoAnalyzer()
results = analyzer.process_export("data/glooko/export.zip")

# Create DataFrame from time in range
tir_df = pd.DataFrame([results["time_in_range"]])
display(tir_df)

# Visualize patterns
patterns_df = pd.DataFrame([
    {"pattern": "Dawn Phenomenon", "confidence": results["patterns"]["dawn_phenomenon"]["confidence"]},
    {"pattern": "Post-Meal Spikes", "rate": results["patterns"]["post_meal_spikes"]["spike_rate"]},
])
display(patterns_df)
```

---

## Appendix: Data Classes Reference

### CGMReading
```python
@dataclass
class CGMReading:
    timestamp: datetime
    glucose_mg_dl: float
    device: Optional[str] = None
```

### InsulinRecord
```python
@dataclass
class InsulinRecord:
    timestamp: datetime
    units: float
    insulin_type: str  # 'basal' or 'bolus'
    notes: Optional[str] = None
```

### CarbRecord
```python
@dataclass
class CarbRecord:
    timestamp: datetime
    grams: float
    meal_type: Optional[str] = None
    notes: Optional[str] = None
```

### Analysis Result Structure
```python
{
    "time_in_range": {
        "total_readings": int,
        "time_in_range_70_180": float,
        "time_below_70": float,
        "time_above_180": float,
        "time_above_250": float,
        "average_glucose": float,
        "glucose_std": float,
        "coefficient_of_variation": float,
        "estimated_a1c": float,
    },
    "patterns": {
        "dawn_phenomenon": {...},
        "post_meal_spikes": {...},
        "insulin_sensitivity": {...},
        "exercise_impact": {...},
    },
    "recommendations": [...],
    "analysis_period": {
        "start": str,
        "end": str,
        "days": int,
    },
    "data_summary": {...},
    "anomalies": [...],
    "disclaimer": str,
    "safety_audit": {...},
}
```

---

*Last updated: January 2026*

*For questions about this integration, see the main project documentation or consult your healthcare team for medical questions.*
