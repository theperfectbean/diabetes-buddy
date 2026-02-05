# A/B Testing & Device Personalization Experimentation Guide

## Overview

This document explains the A/B testing framework for validating the hybrid RAG+parametric knowledge approach against pure RAG, with integrated device personalization and statistical rigor.

## Architecture

### Experimentation Flow

```
User Query 
  ↓
Session Hash (SHA-256) → Deterministic Cohort Assignment (50/50 split)
  ↓
├─ Control Cohort (50%): Pure RAG, min_chunks=3, parametric disabled
└─ Treatment Cohort (50%): Hybrid RAG+parametric, full knowledge blend
  ↓
Response with Cohort Metadata
  ↓
Log to ab_test_assignments.csv (anonymized session_id_hash)
  ↓
Collect User Feedback → Log to feedback.csv
  ↓
Live Analytics Dashboard
```

### Device Personalization Flow

```
PDF Upload 
  ↓
Device Detection (metadata/filename/content) → Confidence scores
  ↓
UI Confirmation (show detected devices, user can override)
  ↓
Store in data/users/{session_hash}/devices.json
  ↓
RAG Retrieval 
  ↓
Apply +0.2 Confidence Boost to Matching Collections
  ↓
Regularized Feedback Loop (decay_factor = 0.1)
```

## Critical Refinements (5 Mandatory)

### Refinement 1: Session ID Anonymization

**Problem:** Session IDs are PII, violating GDPR/HIPAA if stored plaintext.

**Solution:** Hash all session IDs using SHA-256 before storage.

**Implementation:**
```python
from agents.experimentation import anonymize_session_id

session_hash = anonymize_session_id("user-session-123")
# Result: "a1b2c3d4..." (64-char hex, one-way hash)
```

**Properties:**
- Deterministic: Same session_id → same hash
- One-way: No reconstruction possible
- Compliance: GDPR Article 25 (data protection by design)

**Applied to:**
- `ab_test_assignments.csv` (all session_id_hash fields)
- `feedback.csv` (all session_id_hash fields)
- `data/users/{session_hash}/` (directory structure)

---

### Refinement 2: Device Detection Manual Override

**Problem:** Auto-detection errors destroy user trust.

**Solution:** Show detected devices with confidence scores; allow user corrections via UI.

**Endpoint:** `POST /api/devices/override`

**Request:**
```json
{
  "session_id": "user-session-123",
  "pump": "tandem",
  "cgm": "dexcom"
}
```

**Response:**
```json
{
  "success": true,
  "session_id_hash": "a1b2c3d4...",
  "pump": "tandem",
  "cgm": "dexcom",
  "override_source": "user"
}
```

**UI Flow:**
1. Upload PDF → Device Detection
2. Show: "Pump: Tandem (95%), CGM: Dexcom (88%)"
3. Confirm/Edit buttons
4. On confirm: Store with `override_source="user"`

**Success Metric:** Manual override rate < 20% (indicates good detection).

---

### Refinement 3: Statistical Power Analysis

**Problem:** min_sample_size=100 gives only 30% power, risks Type II errors (false negatives).

**Solution:** Calculate minimum sample size for 5% effect at 80% power.

**Formula (Proportions Test):**
```
For baseline=70%, target=75% (5% absolute effect)
α=0.05 (significance), power=0.80
n ≈ 620 per cohort
```

**Config:**
```yaml
experimentation:
  experiments:
    - name: "hybrid_vs_pure_rag"
      min_sample_size: 620  # Both cohorts must reach this
      significance_threshold: 0.05
```

**Rationale:** 30-day experiment allows sufficient samples; prevents Type II error.

**Verification:** See dashboard endpoint `/api/experiments/status`:
```json
{
  "min_sample_size": 620,
  "control_n": 650,
  "treatment_n": 645,
  "min_sample_size_reached": true
}
```

---

### Refinement 4: Feedback Loop Regularization

**Problem:** Single negative feedback destroys good boost (e.g., -0.1 per event hits 0 in 3 events).

**Solution:** Implement decaying learning rate based on feedback count.

**Formula:**
```
effective_rate = base_rate / (1 + decay_factor * feedback_count)
```

**Example with base=0.1, decay=0.1:**
- After 1st feedback: 0.1 / 1.1 ≈ 0.0909
- After 5th feedback: 0.1 / 1.5 ≈ 0.0667
- After 10th feedback: 0.1 / 2.0 = 0.0500

**Effect:** Early feedback strong impact, later feedback diminishing, boost stabilizes.

**Implementation:**
```python
from agents.device_personalization import PersonalizationManager

manager = PersonalizationManager(config=config)

# Track feedback count in BoostAdjustmentState
state = manager.adjust_boost_from_feedback(
    session_id="user-123",
    device_type="pump",
    manufacturer="tandem",
    feedback_delta=-0.05,  # User said boost was too strong
)

print(f"Feedback #{state.feedback_count}: effective_rate={state.adjustment_history[-1]['effective_learning_rate']:.4f}")
```

**Tracking:** Log `effective_learning_rate` and `feedback_count` in debug messages.

---

### Refinement 5: Experiment Dashboard Endpoint

**Problem:** No real-time view of A/B test progress; hard to decide when to declare winner.

**Solution:** Create `GET /api/experiments/status` returning live statistics.

**Endpoint:** `GET /api/experiments/status`

**Response:**
```json
{
  "experiment": "hybrid_vs_pure_rag",
  "control_n": 650,
  "treatment_n": 645,
  "control_helpful_rate": 0.700,
  "treatment_helpful_rate": 0.752,
  "min_sample_size": 620,
  "min_sample_size_reached": true,
  "p_value": 0.0234,
  "t_statistic": 2.271,
  "cohens_d": 0.112,
  "is_significant": true,
  "effect_size": "small",
  "winner": "treatment",
  "recommendation": "✅ WINNER: Treatment (hybrid RAG+parametric) improved helpful rate by 5.2%. Ready to roll out (p=0.0234)."
}
```

**Merges:** `ab_test_assignments.csv` + `feedback.csv` for real-time analysis.

**Rationale:** Makes A/B testing transparent and actionable.

---

## Configuration

### Experimentation Section (config/hybrid_knowledge.yaml)

```yaml
experimentation:
  enabled: false  # Disabled by default (must be explicitly enabled)
  experiments:
    - name: "hybrid_vs_pure_rag"
      cohorts:
        control: 50
        treatment: 50
      metrics: [feedback_score, response_time, parametric_ratio, sources_used]
      duration_days: 30
      min_sample_size: 620
      significance_threshold: 0.05
```

### Personalization Section (config/hybrid_knowledge.yaml)

```yaml
personalization:
  enabled: true
  device_priority_boost: 0.2  # Base boost (+0.2 confidence)
  max_boost: 0.3              # Cap boost adjustment
  learning_rate: 0.1          # Base learning rate for feedback
  decay_factor: 0.1           # Regularization decay
  feedback_window_days: 30    # How long to track feedback
  auto_device_detection: true # Enable auto-detection
```

---

## Statistical Concepts

### T-Test for Binary Outcomes

We use a two-sample t-test to compare helpful rates between cohorts:

```
H0: control_rate = treatment_rate
H1: control_rate ≠ treatment_rate
α = 0.05 (significance level)
```

**Calculation:**
```python
from scipy import stats

t_stat = (treatment_rate - control_rate) / pooled_se
p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df))
```

### Cohen's d (Effect Size)

Measures standardized difference between groups:

```
Cohen's d = (treatment_rate - control_rate) / pooled_std
```

**Categories:**
- d < 0.2: Negligible
- 0.2 ≤ d < 0.5: Small
- 0.5 ≤ d < 0.8: Medium
- d ≥ 0.8: Large

### Declaring Winner

**Criteria for Treatment Victory:**
1. Sample Size: ≥ 620 per cohort
2. Statistical Significance: p-value < 0.05 (two-tailed)
3. Effect Size: Helpful rate ≥ 5% absolute improvement
4. Performance: p95 response time < 3 seconds
5. User Satisfaction: Qualitative feedback confirms reduced friction

If all met → Roll out hybrid to 100%, sunset pure RAG.

---

## Data Files

### ab_test_assignments.csv

Tracks every query and its cohort assignment:

```csv
created_at,session_id_hash,experiment,cohort,query,metadata
2026-02-02T12:00:00+00:00,a1b2c3d4...,hybrid_vs_pure_rag,control,"What is T1D?","{}"
```

**Key Points:**
- `session_id_hash`: SHA-256 hash (no plaintext session ID)
- `experiment`: Experiment name
- `cohort`: "control" or "treatment"
- `query`: User query text
- `metadata`: JSON object (empty, extensible)

### feedback.csv

User feedback on response quality:

```csv
timestamp,session_id_hash,feedback,primary_source_type,response_time_ms
2026-02-02T12:01:00+00:00,a1b2c3d4...,helpful,rag,1234
```

**Fields:**
- `timestamp`: When feedback was recorded
- `session_id_hash`: User (anonymized)
- `feedback`: "helpful" or "not-helpful"
- `primary_source_type`: "rag", "parametric", or "hybrid"
- `response_time_ms`: Response time in milliseconds

### data/users/{session_hash}/devices.json

User's confirmed device choices:

```json
{
  "session_id_hash": "a1b2c3d4...",
  "pump": "tandem",
  "cgm": "dexcom",
  "override_source": "user",
  "detected_at": "2026-02-02T12:00:00+00:00"
}
```

### data/users/{session_hash}/boost_{device_type}_{manufacturer}.json

Boost adjustment state (e.g., `boost_pump_tandem.json`):

```json
{
  "session_id_hash": "a1b2c3d4...",
  "device_type": "pump",
  "manufacturer": "tandem",
  "feedback_count": 5,
  "current_boost": 0.195,
  "last_adjusted_at": "2026-02-02T12:05:00+00:00",
  "adjustment_history": [
    {
      "timestamp": "2026-02-02T12:01:00+00:00",
      "feedback_delta": 0.05,
      "effective_learning_rate": 0.1000,
      "old_boost": 0.2000,
      "adjustment": 0.0050,
      "new_boost": 0.2050,
      "feedback_count": 1
    }
  ]
}
```

---

## API Endpoints

### GET /api/experiments/status

Get live A/B test statistics.

**Response:** See Refinement 5 for full structure.

### POST /api/devices/override

Override auto-detected devices.

**Request:**
```json
{
  "session_id": "user-session-123",
  "pump": "tandem",
  "cgm": "dexcom"
}
```

**Response:** See Refinement 2 for full structure.

### GET /api/feedback-stats

Get general feedback analytics (existing, enhanced with cohort analysis).

**Response:**
```json
{
  "total_responses": 1000,
  "helpful_rate": 0.75,
  "source_performance": {
    "rag": {"helpful_rate": 0.70, "total_responses": 500},
    "parametric": {"helpful_rate": 0.80, "total_responses": 300},
    "hybrid": {"helpful_rate": 0.75, "total_responses": 200}
  },
  "rag_correlation": 0.05
}
```

---

## Validation Checklist

### Refinement 1 (Anonymization)
- [ ] `anonymize_session_id()` returns SHA-256 hash
- [ ] Same session_id → same hash (deterministic)
- [ ] All CSVs use `session_id_hash`, not raw session_id
- [ ] All JSONs use `session_id_hash` in directory paths
- [ ] No plaintext session IDs in logs

### Refinement 2 (Device Override)
- [ ] UI shows detected devices with confidence %
- [ ] Confirm/Edit buttons work
- [ ] `POST /api/devices/override` accepts corrections
- [ ] User corrections saved with `override_source='user'`
- [ ] Manual override rate < 20%

### Refinement 3 (Power Analysis)
- [ ] `min_sample_size = 620`
- [ ] Formula documented
- [ ] For baseline=70%, target=75%, α=0.05, power=0.80
- [ ] Winner only declared after 620+ per cohort

### Refinement 4 (Regularization)
- [ ] Decaying learning rate: `0.1 / (1 + 0.1 * feedback_count)`
- [ ] `feedback_count` tracked in `BoostAdjustmentState`
- [ ] After 5 feedbacks: rate ≈ 0.067
- [ ] Boost stabilizes, doesn't oscillate
- [ ] Single negative feedback doesn't destroy boost

### Refinement 5 (Dashboard)
- [ ] `GET /api/experiments/status` returns live statistics
- [ ] Shows n, helpful_rate, response_time, p_value, t_statistic, Cohen's d
- [ ] `min_sample_size_reached` flag accurate
- [ ] Winner shows 'treatment', 'control', or None
- [ ] Recommendation text actionable

### General
- [ ] Cohort assignment deterministic
- [ ] Cohort split ~50/50 over 1000 sessions
- [ ] Control disables parametric (spot-check 10 queries)
- [ ] Device detection works for 8 pumps, 3 CGMs
- [ ] Confidence boost +0.2, capped at 1.0, floored at 0.0
- [ ] All existing 42 tests pass
- [ ] New tests 80%+ coverage
- [ ] No performance regression (p95 < 3s)

---

## Troubleshooting

### Issue: Experiment status shows no data

**Cause:** No feedback logged yet.

**Fix:** Send queries and log feedback via `POST /api/feedback`.

### Issue: Cohort assignment inconsistent

**Cause:** ExperimentManager config changed mid-experiment.

**Fix:** Keep config stable or clear `ab_test_assignments.csv` and start fresh.

### Issue: Device boost not applying

**Cause:** `personalization_manager` not set on researcher.

**Fix:** Ensure `unified_agent` initializes personalization manager and injects it:
```python
unified_agent.researcher.set_personalization_manager(
    unified_agent.personalization_manager
)
```

### Issue: Feedback decay rate is constant

**Cause:** `decay_factor` set to 0.

**Fix:** Set `decay_factor: 0.1` in config.

---

## References

- GDPR Article 25: Data Protection by Design
- Cochran's formula: Two-sample proportion test power analysis
- Cohen's d: Effect size for proportions
- Scipy stats: t-test and CDF calculations

---

**Last Updated:** 2026-02-02
