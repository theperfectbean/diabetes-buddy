# Implementation Plan: A/B Testing & Device Personalization (REFINED)

**Status:** Planning Phase  
**Objective:** Validate psychological friction reduction hypothesis through A/B testing + device-specific personalization with privacy compliance and statistical rigor  
**Scope:** 5 new modules + 3 modified modules + 4 new test files + dashboard endpoint  

**Critical Refinements Applied:**
1. ✅ Session ID anonymization (SHA-256, GDPR/HIPAA compliance)
2. ✅ Device detection manual override UI (transparency + user control)
3. ✅ Statistical power analysis (620 samples per cohort at 80% power)
4. ✅ Feedback loop regularization (decaying learning rate)
5. ✅ Experiment dashboard endpoint (real-time monitoring)

---

## 1. ARCHITECTURE OVERVIEW

### Experimentation Framework Flow
```
User Query
  ↓
[Session ID Hash] → Cohort Assignment (deterministic)
  ├─ Control (50%): Pure RAG, min_chunks=3, no parametric
  └─ Treatment (50%): Hybrid RAG+parametric (existing)
  ↓
[Response Generation with Cohort Metadata]
  ↓
[Log to ab_test_assignments.csv + feedback tracking]
  ↓
[Analytics via /api/feedback-stats with cohort breakdown]
```

### Device Personalization Flow
```
User PDF Upload
  ↓
[Device Detection] → Extract manufacturer/model
  ├─ Tandem, Medtronic, Omnipod, Ypsomed (pumps)
  └─ Dexcom, Libre, Guardian (CGMs)
  ↓
[Show User Confirmation UI with Detected Devices + Confidence Scores]
  ├─ User clicks "Confirm" → Accept auto-detection
  └─ User clicks "Edit" → POST /api/devices/override with corrections
  ↓
[Store in data/users/{session_hash}/devices.json]  ← Session ID hashed
  ↓
[Query RAG Retrieval]
  ├─ Base retrieval via ChromaDB
  ├─ Check user device profile
  └─ Apply confidence boost to matching collections
  ↓
[Feedback Loop Adjustment with Regularization]
  ├─ Decaying learning rate: effective_rate = 0.1 / (1 + 0.1 * feedback_count)
  ├─ Thumbs-down: reduce boost by effective_rate
  └─ Thumbs-up: increase boost by effective_rate
```

### Critical Refinements Explained

#### Refinement 1: Session ID Anonymization (Privacy/Security)
**Problem:** Session IDs are personally identifiable information (PII); storing them in plaintext violates GDPR/HIPAA.
**Solution:** Hash all session IDs using SHA-256 before storage in any CSV or JSON file.
- Function: `anonymize_session_id(session_id: str) -> str` in `agents/experimentation.py`
- Applied to: ab_test_assignments.csv, response_quality.csv, boost_adjustments.json, devices.json
- Key insight: Hashing is one-way (no PII reconstruction) but deterministic (same session → same hash)
- Compliance: Addresses Article 25 (GDPR: data protection by design)

#### Refinement 2: Device Detection Manual Override (Trust & Transparency)
**Problem:** Auto-detection can be wrong; users lose trust if their device is misidentified.
**Solution:** Show detected devices with confidence scores, allow user corrections.
- UI Flow:
  1. User uploads PDF
  2. System detects devices: "Pump: Tandem (95%), CGM: Dexcom (88%)"
  3. User clicks "Confirm" or "Edit"
  4. If "Edit": Modal to select correct devices from dropdown
  5. POST /api/devices/override with user selections
- Data tracking: Store `override_source: "user"` vs `override_source: "auto_detected"`
- Rationale: Transparency builds trust; user corrections improve algorithm over time
- Success metric: Manual override rate < 20% indicates good auto-detection

#### Refinement 3: Statistical Power Analysis (5% Effect Size at 80% Power)
**Problem:** With min_sample_size=100, we have ~30% power to detect real effects. Risk of Type II error (false negative).
**Solution:** Calculate minimum sample size using standard formulas.
- Formula: For binary outcome (helpful/not-helpful), assuming baseline=70%, target=75% (5% absolute effect):
  - z_α/2 = 1.96 (two-tailed, α=0.05)
  - z_β = 0.84 (power=0.80, β=0.20)
  - n ≈ 2 * ((z_α/2 + z_β) / effect_size)² * p*(1-p)
  - n ≈ 620 per cohort (both control and treatment)
- Updated config: `min_sample_size: 620` (not 100)
- Verification: Include calculation in docs/EXPERIMENTATION.md with interactive calculator
- Rationale: Prevents declaring false winners; 30-day experiment allows sufficient samples

#### Refinement 4: Feedback Loop Regularization (Decaying Learning Rate)
**Problem:** Single negative feedback event can destroy a good boost (e.g., -0.1 per event can hit 0 in 3 events).
**Solution:** Implement decaying learning rate based on feedback count.
- Formula: `effective_rate = base_rate / (1 + decay_factor * feedback_count)`
- Example with base_rate=0.1, decay_factor=0.1:
  - After 1st feedback: rate = 0.1 / 1.1 = 0.091
  - After 5th feedback: rate = 0.1 / 1.5 = 0.067
  - After 10th feedback: rate = 0.1 / 2.0 = 0.050
- Effect: Early feedback strongly adjusts boost; later feedback has smaller impact
- Prevents: Overfitting to noisy individual feedback; boost stabilizes after ~5-10 events
- Tracking: Log `effective_learning_rate` and `feedback_count` in debug messages

#### Refinement 5: Experiment Dashboard Endpoint (Operational Transparency)
**Problem:** No real-time view of A/B test progress; hard to decide when to declare winner.
**Solution:** Create GET /api/experiments/status endpoint showing live statistics.
- Response structure:
  ```json
  {
    "experiments": [
      {
        "name": "hybrid_vs_pure_rag",
        "status": "running",
        "start_date": "2025-02-01",
        "end_date": "2025-03-03",
        "days_remaining": 25,
        "cohorts": {
          "control": {
            "n": 345,
            "helpful_rate": 0.68,
            "avg_response_time_ms": 1250,
            "avg_parametric_ratio": 0.0
          },
          "treatment": {
            "n": 352,
            "helpful_rate": 0.72,
            "avg_response_time_ms": 1380,
            "avg_parametric_ratio": 0.35
          }
        },
        "statistics": {
          "t_statistic": 1.24,
          "p_value": 0.214,
          "is_significant": false,
          "effect_size": 0.04,
          "min_sample_size_reached": false
        },
        "recommendation": "Continue test - not enough samples yet. Need 620 per cohort, currently 350."
      }
    ]
  }
  ```
- Merges data from: ab_test_assignments.csv + feedback.csv for real-time analysis
- Rationale: Makes A/B testing transparent to team; clear decision criteria when to stop

---

## 2. DELIVERABLES BREAKDOWN

### 2.1 NEW MODULE: `agents/experimentation.py`

**Purpose:** Central experimentation orchestration with privacy-preserving session handling  
**Dependencies:** `yaml`, `hashlib`, `csv`, `pathlib`, `logging`  
**Size:** ~450-550 lines

#### Key Classes:

1. **`ExperimentConfig`** (dataclass)
   - Parsed from `config/hybrid_knowledge.yaml`
   - Fields: `enabled`, `experiments` list with cohorts/metrics/duration, `min_sample_size`, `significance_threshold`

2. **`ExperimentManager`**
   - `__init__(config: dict, project_root: Path)`
   - `anonymize_session_id(session_id: str) -> str` ⭐ NEW - REFINEMENT 1
     - SHA-256 hash of session_id for PII protection
     - Deterministic (same input → same output)
     - One-way (cannot reconstruct original session ID)
     - Logged: `logger.debug(f"Session {session_id} anonymized to {hashed_id}")`
   
   - `get_cohort_assignment(session_id: str) -> str`
     - Hash session_id deterministically
     - Map to cohort based on hash % 100 and split percentages
     - Returns: `'control'` or `'treatment'`
   
   - `log_assignment(session_id: str, cohort: str, query: str, metadata: dict) -> None` ⭐ MODIFIED
     - Appends to `data/analysis/ab_test_assignments.csv`
     - Fields: timestamp, session_id_hash, cohort, query_preview, experiment_name, metadata_json
     - Session ID stored as SHA-256 hash (GDPR/HIPAA compliant)
     - Example: `timestamp,sess_hash_a1b2c3...,control,"how to change basal",hybrid_vs_pure_rag,{...}`
   
   - `should_run_experiment(experiment_name: str) -> bool`
     - Check if enabled and within duration_days

3. **`CohortConfig`** (dataclass)
   - Defines behavior for control vs treatment
   - `apply_control_constraints(rag_config: dict) -> dict`
     - Override `min_chunks` to 3
     - Disable parametric fallback
     - Return modified config

#### Key Methods:

```python
@staticmethod
def anonymize_session_id(session_id: str) -> str:
    """
    SHA-256 hash session ID for GDPR/HIPAA compliance.
    
    Rationale (Refinement 1):
    - One-way hash prevents PII reconstruction
    - Deterministic allows cohort consistency
    - No database lookup needed for hashing
    """
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]

@staticmethod
def hash_session_to_cohort(session_id: str, percentages: dict) -> str:
    """Deterministic cohort assignment via hashing."""
    hash_value = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 100
    cumulative = 0
    for cohort, percentage in percentages.items():
        cumulative += percentage
        if hash_value < cumulative:
            return cohort
    return 'control'  # default

def validate_split(percentages: dict) -> None:
    """Ensure cohorts sum to 100%."""
    total = sum(percentages.values())
    if total != 100:
        raise ValueError(f"Cohort percentages must sum to 100%, got {total}")
```

#### CSV Output Format (with Session Anonymization):
```csv
timestamp,session_id_hash,cohort,query_preview,experiment_name,min_chunks_override,parametric_enabled,metadata
2025-02-02T10:30:45Z,a1b2c3d4e5f6g7h8,control,"how to change basal",hybrid_vs_pure_rag,3,false,"{""rag_quality"": 0.65}"
2025-02-02T10:31:12Z,x9y8z7w6v5u4t3s2,treatment,"sensor warm up",hybrid_vs_pure_rag,5,true,"{""rag_quality"": 0.82}"
```

**Privacy Guarantees:**
- Session hashes stored, not original IDs
- Same session → same hash → consistent cohort assignment
- Hashes unrecoverable (SHA-256)
- Satisfies GDPR Article 25 (privacy by design)

### 2.2 NEW MODULE: `agents/device_detection.py`

**Purpose:** Manufacturer/model detection + user device profiling with override capability  
**Dependencies:** `PyPDF2`, `json`, `pathlib`, `re`, `logging`  
**Size:** ~400-500 lines

#### Key Classes:

1. **`DeviceDetector`**
   - `__init__()`
   - `detect_from_pdf_metadata(pdf_path: Path) -> dict`
     - Extract title, subject, producer from PDF metadata
     - Pattern match against known manufacturers
     - Returns: `{'pump': 'tandem_tslim', 'cgm': 'dexcom_g7', 'confidence': 0.9}`
   
   - `detect_from_filename(filename: str) -> dict`
     - Fallback pattern matching on filename
     - E.g., "TandemTSlimX2.pdf" → `{'pump': 'tandem_tslim', 'confidence': 0.6}`
   
   - `detect_from_content_sample(pdf_path: Path, pages: int = 5) -> dict`
     - Read first N pages, search for manufacturer keywords
     - Returns: `{'pump': 'medtronic_780g', 'cgm': 'guardian4', 'confidence': 0.8}`

2. **`ManufacturerKeywords`** (dataclass/constants)
   ```python
   PUMP_KEYWORDS = {
       'tandem': ['t:slim', 'tandem', 'basal-iq'],
       'medtronic': ['670g', '780g', 'minimed', 'paradigm'],
       'omnipod': ['omnipod', 'dash', 'horizon'],
       'ypsomed': ['ypsopump', 'mylife'],
   }
   CGM_KEYWORDS = {
       'dexcom': ['dexcom', 'g6', 'g7'],
       'libre': ['freestyle', 'libre'],
       'guardian': ['guardian', 'medtronic sensor'],
   }
   ```

3. **`UserDeviceProfile`** (dataclass)
   - `session_id_hash: str` ⭐ MODIFIED - now stores hashed session ID
   - `pump: Optional[str]`  # e.g., 'tandem_tslim'
   - `cgm: Optional[str]`   # e.g., 'dexcom_g7'
   - `detection_confidence: dict`
   - `detection_methods: dict` # which method detected each device
   - `override_source: Optional[str]` # ⭐ NEW - 'auto_detected' or 'user' (Refinement 2)
   - `created_at: datetime`
   - `updated_at: datetime`

4. **`UserDeviceManager`**
   - `__init__(project_root: Path)`
   - `load_profile(session_id_hash: str) -> UserDeviceProfile`
     - Load from `data/users/{session_id_hash}/devices.json`
     - Return default if doesn't exist
   
   - `save_profile(profile: UserDeviceProfile) -> None`
     - Write to JSON with ISO timestamps
   
   - `update_from_upload(session_id_hash: str, pdf_path: Path) -> UserDeviceProfile`
     - Run all 3 detection methods
     - Weight results by confidence
     - Merge with existing profile
     - Set override_source to 'auto_detected'
     - Save and return
   
   - `apply_user_override(session_id_hash: str, pump: Optional[str], cgm: Optional[str]) -> UserDeviceProfile` ⭐ NEW (Refinement 2)
     - User corrects auto-detected devices via UI
     - Update profile with user selections
     - Set override_source to 'user'
     - Log the correction for algorithm improvement
     - Return updated profile

#### Storage Format (data/users/{session_id_hash}/devices.json):
```json
{
  "session_id_hash": "a1b2c3d4e5f6g7h8",
  "pump": "tandem_tslim",
  "cgm": "dexcom_g7",
  "detection_confidence": {
    "pump": 0.95,
    "cgm": 0.88
  },
  "detection_methods": {
    "pump": "content_sample",
    "cgm": "metadata"
  },
  "override_source": "auto_detected",
  "created_at": "2025-02-01T10:00:00Z",
  "updated_at": "2025-02-02T11:30:00Z"
}
```

#### Key Methods:

```python
def get_device_collections(profile: UserDeviceProfile) -> list[str]:
    """Map device to ChromaDB collection names."""
    collections = []
    if profile.pump:
        collections.append(f"device_{profile.pump}")
    if profile.cgm:
        collections.append(f"device_{profile.cgm}")
    return collections

def merge_detection_results(*detections: dict) -> dict:
    """Combine multiple detection methods, weighted by confidence."""
    # Simple weighted average if multiple detections
    
def validate_device_type(device_name: str, device_type: str) -> bool:
    """Validate that device_name is valid for device_type (pump/cgm)."""
    valid_pumps = ['tandem_tslim', 'medtronic_670g', 'medtronic_780g', 'omnipod', 'ypsomed']
    valid_cgms = ['dexcom_g6', 'dexcom_g7', 'libre', 'guardian']
    
    if device_type == 'pump':
        return device_name in valid_pumps
    elif device_type == 'cgm':
        return device_name in valid_cgms
    return False
```

**Refinement 2 Integration:**
- POST /api/devices/override endpoint (see web/app.py section below)
- User sees detected devices with confidence scores after upload
- UI allows "Confirm" (auto-detection) or "Edit" (manual correction)
- Corrections tracked for quality metrics
- Success metric: override_rate < 20%

### 2.3 NEW MODULE: `agents/device_personalization.py`

**Purpose:** Confidence boost application + regularized feedback loop adjustment  
**Dependencies:** `json`, `pathlib`, `dataclass`, `logging`  
**Size:** ~350-450 lines

#### Key Classes:

1. **`PersonalizationConfig`** (from yaml)
   ```yaml
   personalization:
     device_priority_boost: 0.2  # +0.2 to confidence
     max_boost: 0.3              # Cap at 0.3
     learning_rate: 0.1          # Base learning rate
     decay_factor: 0.1           # For regularization formula
     feedback_window_days: 30    # Consider recent feedback
   ```

2. **`PersonalizationManager`**
   - `__init__(config: dict, project_root: Path)`
   - `apply_device_boost(chunks: list[SearchResult], session_id_hash: str, config: dict) -> list[SearchResult]`
     - Load user device profile
     - For each chunk, check if matches user's device collections
     - If match: `chunk.confidence = min(chunk.confidence + boost, 1.0)`
     - Return re-ranked chunks by confidence
   
   - `calculate_effective_learning_rate(feedback_count: int, base_rate: float, decay_factor: float) -> float` ⭐ NEW (Refinement 4)
     - Regularized learning rate formula
     - `effective_rate = base_rate / (1 + decay_factor * feedback_count)`
     - Prevents overfitting to noisy individual feedback
     - Example: 0.1 / (1 + 0.1 * 5) = 0.067 after 5 feedbacks
   
   - `adjust_boost_from_feedback(session_id_hash: str, chunk_source: str, feedback: str) -> float` ⭐ MODIFIED
     - Load user profile's current boost adjustment and feedback count
     - Calculate effective_learning_rate using regularized formula
     - If feedback == 'helpful': increase boost by effective_rate
     - If feedback == 'not-helpful': decrease boost by effective_rate
     - Clamp to [0.0, max_boost]
     - Increment feedback_count
     - Save adjustment state with new feedback_count
     - Log effective_learning_rate and feedback_count for debugging
     - Return new boost value

3. **`BoostAdjustmentState`** (dataclass) ⭐ MODIFIED
   - `session_id_hash: str`
   - `source_adjustments: dict[str, float]`  # e.g., {'device_tandem_tslim': 0.15}
   - `feedback_count: dict[str, int]` ⭐ NEW  # e.g., {'device_tandem_tslim': 5}
   - `last_feedback_times: dict[str, datetime]` ⭐ NEW  # for feedback_window_days
   - `updated_at: datetime`

#### Storage (data/users/{session_id_hash}/boost_adjustments.json):
```json
{
  "session_id_hash": "a1b2c3d4e5f6g7h8",
  "source_adjustments": {
    "device_tandem_tslim": 0.25,
    "device_dexcom_g7": 0.20
  },
  "feedback_count": {
    "device_tandem_tslim": 5,
    "device_dexcom_g7": 3
  },
  "last_feedback_times": {
    "device_tandem_tslim": "2025-02-02T11:00:00Z",
    "device_dexcom_g7": "2025-02-02T10:30:00Z"
  },
  "updated_at": "2025-02-02T11:30:00Z"
}
```

#### Key Methods with Regularization:

```python
@staticmethod
def calculate_effective_learning_rate(
    feedback_count: int, 
    base_rate: float = 0.1, 
    decay_factor: float = 0.1
) -> float:
    """
    Calculate regularized learning rate using decay formula.
    
    Rationale (Refinement 4):
    - Early feedback has strong impact
    - Later feedback has diminishing impact
    - Prevents single noisy event from destroying good boost
    - Formula: effective_rate = base_rate / (1 + decay_factor * feedback_count)
    
    Examples (base_rate=0.1, decay_factor=0.1):
    - feedback_count=0: rate = 0.1 / 1 = 0.100 (first feedback strongest)
    - feedback_count=5: rate = 0.1 / 1.5 = 0.067
    - feedback_count=10: rate = 0.1 / 2.0 = 0.050
    """
    return base_rate / (1.0 + decay_factor * feedback_count)

def get_current_boost(session_id_hash: str, source: str, base_boost: float = None) -> float:
    """Get current boost for a source, defaulting to config value."""
    # Load boost_adjustments.json
    # Return source-specific adjustment or default (device_priority_boost from config)

def apply_feedback_learning(
    session_id_hash: str, 
    source: str, 
    feedback: str, 
    config: dict
) -> dict:
    """
    Update boost based on feedback with regularization.
    
    Returns: {
        'new_boost': float,
        'previous_boost': float,
        'delta': float,
        'effective_learning_rate': float,
        'feedback_count': int
    }
    """
    state = self._load_adjustment_state(session_id_hash)
    current_boost = state.source_adjustments.get(source, config['device_priority_boost'])
    feedback_count = state.feedback_count.get(source, 0)
    
    # Calculate regularized learning rate
    effective_rate = self.calculate_effective_learning_rate(
        feedback_count,
        config['learning_rate'],
        config.get('decay_factor', 0.1)
    )
    
    # Apply feedback
    if feedback == 'helpful':
        delta = effective_rate
    else:
        delta = -effective_rate
    
    new_boost = max(0.0, min(current_boost + delta, config['max_boost']))
    
    # Update state
    state.source_adjustments[source] = new_boost
    state.feedback_count[source] = feedback_count + 1
    state.last_feedback_times[source] = datetime.now()
    self._save_adjustment_state(session_id_hash, state)
    
    # Log for debugging
    logger.debug(
        f"Boost adjustment: source={source}, feedback={feedback}, "
        f"old_boost={current_boost:.3f}, new_boost={new_boost:.3f}, "
        f"effective_rate={effective_rate:.3f}, feedback_count={feedback_count + 1}"
    )
    
    return {
        'new_boost': new_boost,
        'previous_boost': current_boost,
        'delta': delta,
        'effective_learning_rate': effective_rate,
        'feedback_count': feedback_count + 1
    }
```

**Refinement 4 Impact:**
- Early feedback strongly influences boost (rate ≈ 0.1)
- Boost stabilizes after ~5-10 feedback events
- Prevents overfitting to single negative/positive events
- Logged for transparency and debugging

### 2.4 MODIFY: `config/hybrid_knowledge.yaml`

**Add sections:**

```yaml
# === NEW SECTIONS ===

experimentation:
  enabled: false  # Disabled by default to avoid disrupting production
  experiments:
    - name: "hybrid_vs_pure_rag"
      description: "Validate that hybrid RAG+parametric reduces friction vs pure RAG"
      cohorts:
        control: 50    # Pure RAG only
        treatment: 50  # Hybrid RAG+parametric
      metrics:
        - feedback_score      # avg helpful/not-helpful rate
        - response_time       # latency
        - parametric_ratio    # % parametric in response
        - sources_used        # diversity
      duration_days: 30
      min_sample_size: 620  # ⭐ REFINEMENT 3: Statistical power analysis
      # Calculated for: 5% absolute effect (70% → 75%), 80% power, α=0.05
      # Formula: n ≈ 2 * ((z_α/2 + z_β) / effect_size)² * p*(1-p)
      # Result: 620 per cohort (control + treatment)
      significance_threshold: 0.05

personalization:
  enabled: true  # Can be enabled independently
  device_priority_boost: 0.2   # +0.2 confidence to user's device sources
  max_boost: 0.3               # Cap maximum boost
  learning_rate: 0.1           # Base learning rate
  decay_factor: 0.1            # ⭐ REFINEMENT 4: Regularization factor
  # Effective rate = 0.1 / (1 + 0.1 * feedback_count)
  feedback_window_days: 30     # Consider recent feedback
  auto_device_detection: true  # Scan PDFs for device info
  
# === EXISTING SECTIONS (unchanged) ===
rag_quality:
  min_chunks: 3
  min_confidence: 0.7
  min_sources: 2
  min_chunk_confidence: 0.35

parametric_usage:
  max_ratio: 0.7
  confidence_score: 0.6

safety:
  enhanced_check_threshold: 0.3

emergency_detection:
  enabled: true
  severity_thresholds:
    critical: 0.9
    high: 0.7
    medium: 0.5
  response_templates:
    critical: "⚠️ MEDICAL EMERGENCY detected..."
    high: "⚠️ URGENT MEDICAL ATTENTION needed..."
    medium: "⚠️ MEDICAL ATTENTION recommended..."

logging:
  level: "INFO"
  file_path: "logs/hybrid_system.log"
  max_size_mb: 10
  backup_count: 5

knowledge_monitoring:
  staleness_threshold_days: 30
  critical_threshold_days: 90
```

**Notes on Refinements:**
- **Refinement 1 (Session Anonymization):** Session IDs hashed before storage
- **Refinement 3 (Power Analysis):** min_sample_size=620 ensures 80% power for 5% effect
- **Refinement 4 (Regularization):** decay_factor controls feedback learning rate decay

---

### 2.5 MODIFY: `agents/unified_agent.py`

**Changes:** Add experimentation framework integration (40-50 lines of changes)

#### In `__init__`:
```python
def __init__(self, project_root: Optional[Path] = None):
    # ... existing code ...
    self.project_root = project_root
    self.analysis_dir = project_root / "data" / "analysis"
    self.config = self._load_hybrid_config()
    
    # NEW: Initialize experimentation if enabled
    if self.config.get('experimentation', {}).get('enabled', False):
        from .experimentation import ExperimentManager
        self.experiment_manager = ExperimentManager(self.config, project_root)
    else:
        self.experiment_manager = None
    
    # NEW: Initialize personalization if enabled
    if self.config.get('personalization', {}).get('enabled', False):
        from .device_personalization import PersonalizationManager
        self.personalization_manager = PersonalizationManager(self.config, project_root)
    else:
        self.personalization_manager = None
    
    self.researcher = ResearcherAgent(project_root=project_root)
```

#### In `query_stream()` method (add after cohort check):
```python
def query_stream(self, query: str, session_id: Optional[str] = None) -> Generator[str, None, None]:
    # ... existing safety checks ...
    
    # NEW: Get cohort assignment if experimentation enabled
    cohort = None
    if self.experiment_manager:
        cohort = self.experiment_manager.get_cohort_assignment(session_id or "default")
        self.experiment_manager.log_assignment(
            session_id=session_id or "default",
            cohort=cohort,
            query=query,
            metadata={'query_length': len(query)}
        )
        logger.info(f"Cohort assignment: {cohort} for session {session_id}")
    
    # ... existing code to get raw_results ...
    
    # NEW: If control cohort, apply constraints
    if cohort == 'control':
        # Temporarily override config for this query
        original_min_chunks = self.config['rag_quality']['min_chunks']
        original_parametric_max = self.config['parametric_usage']['max_ratio']
        
        self.config['rag_quality']['min_chunks'] = 3
        self.config['parametric_usage']['max_ratio'] = 0.0  # Disable parametric
        logger.debug(f"Applied control cohort constraints")
    
    try:
        # ... rest of query_stream logic ...
    finally:
        # Restore config if control cohort
        if cohort == 'control':
            self.config['rag_quality']['min_chunks'] = original_min_chunks
            self.config['parametric_usage']['max_ratio'] = original_parametric_max
```

#### In `UnifiedResponse` dataclass:
```python
@dataclass
class UnifiedResponse:
    # ... existing fields ...
    cohort: Optional[str] = None  # NEW: Track which cohort generated response
```

---

### 2.6 MODIFY: `agents/researcher_chromadb.py`

**Changes:** Add device personalization boost (60-80 lines of changes)

#### In `query_knowledge()` method (after retrieving chunks):
```python
def query_knowledge(self, query: str, top_k: int = 5, session_id: Optional[str] = None) -> List[SearchResult]:
    """Query knowledge base with optional device personalization boost."""
    
    # ... existing retrieval logic ...
    results = self._retrieve_and_rank(query, top_k)
    
    # NEW: Apply device personalization boost if available
    if session_id and hasattr(self, 'personalization_manager'):
        results = self.personalization_manager.apply_device_boost(
            results,
            session_id,
            self.config
        )
        logger.debug(f"Applied device personalization boost for session {session_id}")
    
    return results
```

#### New method in `ResearcherAgent`:
```python
def set_personalization_manager(self, manager) -> None:
    """Inject personalization manager (dependency injection)."""
    self.personalization_manager = manager
```

#### Update `__init__` in ResearcherAgent:
```python
def __init__(self, ...):
    # ... existing code ...
    self.personalization_manager = None  # To be injected by UnifiedAgent
```

---

### 2.7 MODIFY: `web/app.py`

**Changes:** Enhance `/api/feedback-stats` endpoint + dashboard + device override (150-200 lines total)

#### 1. Add new endpoint: GET /api/experiments/status ⭐ NEW (Refinement 5)

```python
@app.get("/api/experiments/status")
async def get_experiments_status():
    """
    Return live A/B test statistics for dashboard monitoring.
    
    Refinement 5: Operational transparency
    - Shows progress toward min_sample_size (620 per cohort)
    - Calculates effect size and significance
    - Provides recommendation for stopping test
    """
    try:
        if not FEEDBACK_FILE.exists() or not ASSIGNMENTS_FILE.exists():
            return {
                "experiments": [],
                "message": "No experiment data collected yet"
            }
        
        # Read both files
        import csv
        assignments = []
        feedback = []
        
        with open(ASSIGNMENTS_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                assignments.append(row)
        
        with open(FEEDBACK_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                feedback.append(row)
        
        # Merge assignments with feedback
        feedback_by_cohort = {'control': [], 'treatment': []}
        response_times_by_cohort = {'control': [], 'treatment': []}
        parametric_ratios_by_cohort = {'control': [], 'treatment': []}
        
        for fb in feedback:
            cohort = fb.get('cohort', 'unknown')
            if cohort in feedback_by_cohort:
                feedback_by_cohort[cohort].append(fb['feedback'])
                if fb.get('response_time_ms'):
                    response_times_by_cohort[cohort].append(float(fb['response_time_ms']))
                if fb.get('parametric_ratio'):
                    parametric_ratios_by_cohort[cohort].append(float(fb['parametric_ratio']))
        
        # Calculate cohort statistics
        cohort_stats = {}
        config = load_config()
        min_sample_size = config.get('experimentation', {}).get('experiments', [{}])[0].get('min_sample_size', 620)
        
        for cohort in ['control', 'treatment']:
            feedbacks = feedback_by_cohort[cohort]
            if feedbacks:
                helpful_count = sum(1 for f in feedbacks if f == 'helpful')
                helpful_rate = helpful_count / len(feedbacks)
                
                avg_response_time = (
                    sum(response_times_by_cohort[cohort]) / len(response_times_by_cohort[cohort])
                    if response_times_by_cohort[cohort] else 0
                )
                avg_parametric_ratio = (
                    sum(parametric_ratios_by_cohort[cohort]) / len(parametric_ratios_by_cohort[cohort])
                    if parametric_ratios_by_cohort[cohort] else 0
                )
                
                cohort_stats[cohort] = {
                    'n': len(feedbacks),
                    'helpful_rate': round(helpful_rate, 3),
                    'avg_response_time_ms': round(avg_response_time, 1),
                    'avg_parametric_ratio': round(avg_parametric_ratio, 3)
                }
        
        # Calculate significance
        significance = None
        if 'control' in cohort_stats and 'treatment' in cohort_stats:
            from scipy import stats as scipy_stats
            
            control_scores = [1.0 if f == 'helpful' else 0.0 for f in feedback_by_cohort['control']]
            treatment_scores = [1.0 if f == 'helpful' else 0.0 for f in feedback_by_cohort['treatment']]
            
            if control_scores and treatment_scores:
                t_stat, p_value = scipy_stats.ttest_ind(treatment_scores, control_scores)
                
                # Calculate effect size (Cohen's d)
                control_mean = sum(control_scores) / len(control_scores)
                treatment_mean = sum(treatment_scores) / len(treatment_scores)
                pooled_std = (
                    ((sum((x - control_mean)**2 for x in control_scores) + 
                      sum((x - treatment_mean)**2 for x in treatment_scores)) / 
                     (len(control_scores) + len(treatment_scores) - 2)) ** 0.5
                )
                cohens_d = (treatment_mean - control_mean) / pooled_std if pooled_std > 0 else 0
                
                min_reached = all(cohort_stats[c]['n'] >= min_sample_size for c in ['control', 'treatment'])
                
                significance = {
                    't_statistic': float(t_stat),
                    'p_value': float(p_value),
                    'is_significant': p_value < 0.05,
                    'cohens_d': round(cohens_d, 3),
                    'min_sample_size_reached': min_reached,
                    'winner': (
                        'treatment' if treatment_mean > control_mean else 'control'
                        if min_reached and p_value < 0.05 else None
                    )
                }
        
        # Generate recommendation
        recommendation = None
        if significance:
            if not significance['min_sample_size_reached']:
                remaining_control = min_sample_size - cohort_stats['control']['n']
                remaining_treatment = min_sample_size - cohort_stats['treatment']['n']
                recommendation = (
                    f"Continue test. Need {max(remaining_control, remaining_treatment)} more samples "
                    f"(currently {cohort_stats['control']['n']} control, {cohort_stats['treatment']['n']} treatment)"
                )
            elif significance['is_significant']:
                winner = significance['winner']
                recommendation = (
                    f"✅ WINNER FOUND: {winner} cohort (p={significance['p_value']:.3f}, "
                    f"effect={significance['cohens_d']:.3f}). Ready to rollout."
                )
            else:
                recommendation = (
                    f"❌ NOT SIGNIFICANT: p={significance['p_value']:.3f} (threshold=0.05). "
                    f"Continue test or declare no winner."
                )
        
        return {
            "experiments": [
                {
                    "name": "hybrid_vs_pure_rag",
                    "status": "running",
                    "cohorts": cohort_stats,
                    "statistics": significance,
                    "recommendation": recommendation
                }
            ]
        }
    
    except Exception as e:
        logger.error(f"Failed to get experiments status: {e}")
        return {"error": str(e)}
```

#### 2. Add new endpoint: POST /api/devices/override ⭐ NEW (Refinement 2)

```python
@app.post("/api/devices/override")
async def override_device_detection(request: Request):
    """
    User manually corrects auto-detected device.
    
    Refinement 2: Device detection override UI
    - User sees detected devices with confidence
    - Clicks "Edit" to manually correct
    - POST to this endpoint with corrections
    - Tracked for quality metrics
    """
    try:
        body = await request.json()
        session_id = body.get('session_id')
        pump = body.get('pump')  # e.g., 'tandem_tslim' or None
        cgm = body.get('cgm')    # e.g., 'dexcom_g7' or None
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")
        
        # Anonymize session ID
        from agents.experimentation import ExperimentManager
        session_hash = ExperimentManager.anonymize_session_id(session_id)
        
        # Apply override
        from agents.device_detection import UserDeviceManager
        device_manager = UserDeviceManager(PROJECT_ROOT)
        
        # Validate device types
        valid_pumps = ['tandem_tslim', 'medtronic_670g', 'medtronic_780g', 'omnipod', 'ypsomed', None]
        valid_cgms = ['dexcom_g6', 'dexcom_g7', 'libre', 'guardian', None]
        
        if pump not in valid_pumps:
            raise HTTPException(status_code=400, detail=f"Invalid pump: {pump}")
        if cgm not in valid_cgms:
            raise HTTPException(status_code=400, detail=f"Invalid CGM: {cgm}")
        
        profile = device_manager.apply_user_override(session_hash, pump, cgm)
        
        logger.info(f"Device override applied: {session_hash} → pump={pump}, cgm={cgm}")
        
        return {
            "status": "success",
            "profile": {
                "pump": profile.pump,
                "cgm": profile.cgm,
                "override_source": profile.override_source
            }
        }
    
    except Exception as e:
        logger.error(f"Device override failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 3. Update feedback stats endpoint:
```python
@app.get("/api/feedback-stats")
async def get_feedback_stats():
    """Return feedback analytics with A/B test cohort breakdown if available."""
    try:
        if not FEEDBACK_FILE.exists():
            return {
                "total_responses": 0,
                "helpful_rate": 0.0,
                "source_performance": {},
                "rag_correlation": 0.0,
                "cohort_analysis": None
            }
        
        # Read feedback data
        import csv
        feedback_data = []
        with open(FEEDBACK_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                feedback_data.append(row)
        
        if not feedback_data:
            return {...}
        
        # ... existing calculations ...
        
        # NEW: Cohort analysis if cohort column exists
        cohort_analysis = None
        if all('cohort' in row for row in feedback_data):
            cohort_stats = {}
            for cohort in ['control', 'treatment']:
                cohort_feedback = [row for row in feedback_data if row.get('cohort') == cohort]
                if cohort_feedback:
                    helpful_count = sum(1 for f in cohort_feedback if f['feedback'] == 'helpful')
                    total = len(cohort_feedback)
                    
                    cohort_stats[cohort] = {
                        'n': total,
                        'helpful_rate': helpful_count / total if total > 0 else 0.0,
                        'avg_response_time_ms': statistics.mean([
                            float(f.get('response_time_ms', 0)) 
                            for f in cohort_feedback 
                            if f.get('response_time_ms')
                        ]) or 0,
                        'avg_parametric_ratio': statistics.mean([
                            float(f.get('parametric_ratio', 0)) 
                            for f in cohort_feedback 
                            if f.get('parametric_ratio')
                        ]) or 0,
                    }
            
            # Calculate statistical significance
            if 'control' in cohort_stats and 'treatment' in cohort_stats:
                from scipy import stats as scipy_stats
                
                control_feedback = [row for row in feedback_data if row.get('cohort') == 'control' and row['feedback'] in ['helpful', 'not-helpful']]
                treatment_feedback = [row for row in feedback_data if row.get('cohort') == 'treatment' and row['feedback'] in ['helpful', 'not-helpful']]
                
                if control_feedback and treatment_feedback:
                    control_scores = [1.0 if f['feedback'] == 'helpful' else 0.0 for f in control_feedback]
                    treatment_scores = [1.0 if f['feedback'] == 'helpful' else 0.0 for f in treatment_feedback]
                    
                    t_stat, p_value = scipy_stats.ttest_ind(treatment_scores, control_scores)
                    
                    cohort_stats['significance'] = {
                        't_statistic': float(t_stat),
                        'p_value': float(p_value),
                        'is_significant': p_value < 0.05,
                        'winner': 'treatment' if treatment_scores and control_scores and sum(treatment_scores)/len(treatment_scores) > sum(control_scores)/len(control_scores) else 'control'
                    }
            
            cohort_analysis = cohort_stats
        
        return {
            "total_responses": total_responses,
            "helpful_rate": round(helpful_rate, 3),
            "source_performance": source_performance,
            "rag_correlation": round(rag_correlation, 3),
            "cohort_analysis": cohort_analysis
        }
    
    except Exception as e:
        logger.error(f"Failed to get feedback stats: {e}")
        return {"error": str(e)}
```

#### Update feedback logging in `/api/query` endpoint:
```python
# When logging feedback, add cohort and other metadata
feedback_row = {
    'timestamp': datetime.now().isoformat(),
    'session_id': session_id,
    'cohort': response_metadata.get('cohort', 'unknown'),  # NEW
    'query': query[:200],
    'feedback': feedback,
    'primary_source_type': response_metadata.get('primary_source_type', 'unknown'),
    'rag_ratio': response_metadata.get('rag_ratio', 0),
    'response_time_ms': response_metadata.get('response_time_ms', 0),  # NEW
    'parametric_ratio': response_metadata.get('parametric_ratio', 0),  # NEW
    'knowledge_breakdown': json.dumps(response_metadata.get('knowledge_breakdown', {}))
}
```

---

### 2.8 NEW: `docs/EXPERIMENTATION.md`

**Purpose:** User documentation for experimentation framework  
**Size:** ~500-800 lines

#### Sections:

1. **Overview**
   - Purpose: Validate psychological friction reduction hypothesis
   - Hypothesis: Hybrid RAG+parametric reduces uncertainty vs pure RAG
   - Metrics: Helpfulness, response time, source diversity

2. **Configuration**
   - How to enable in `config/hybrid_knowledge.yaml`
   - Cohort split percentages (must sum to 100)
   - Duration and sample size thresholds

3. **Interpreting Results**
   - Cohort breakdown table
   - T-test significance explanation
   - Effect size calculation
   - Sample queries to run in each cohort

4. **Declaring a Winner**
   - Wait until min_sample_size reached per cohort
   - Verify p_value < 0.05
   - Consider effect size (not just significance)
   - Phase out losing cohort gradually

5. **Running Experiments**
   - Command to check experiment status
   - Export data for analysis
   - Examples of interesting queries

6. **Troubleshooting**
   - Session ID not tracked
   - Cohort split not balanced
   - Feedback not logged

---

## 3. TEST SUITE ADDITIONS

### 3.1 Unit Tests: `tests/test_experimentation.py` (~300 lines)

```python
class TestExperimentManager:
    
    def test_cohort_assignment_deterministic(self):
        """Same session_id always maps to same cohort."""
        manager = ExperimentManager(config, project_root)
        cohort1 = manager.get_cohort_assignment("sess_abc123")
        cohort2 = manager.get_cohort_assignment("sess_abc123")
        assert cohort1 == cohort2
    
    def test_cohort_split_balanced(self):
        """1000 sessions should split ~50/50 for 50/50 config."""
        manager = ExperimentManager({'control': 50, 'treatment': 50}, project_root)
        counts = {'control': 0, 'treatment': 0}
        for i in range(1000):
            cohort = manager.get_cohort_assignment(f"sess_{i:04d}")
            counts[cohort] += 1
        
        control_pct = counts['control'] / 1000 * 100
        treatment_pct = counts['treatment'] / 1000 * 100
        
        assert 40 < control_pct < 60  # Allow ±10% variance
        assert 40 < treatment_pct < 60
    
    def test_assignment_logging(self):
        """Assignments written to CSV correctly."""
        csv_file = tmpdir / "assignments.csv"
        manager = ExperimentManager(config, project_root)
        manager.log_assignment("sess_test", "control", "test query", {})
        
        assert csv_file.exists()
        df = pd.read_csv(csv_file)
        assert len(df) == 1
        assert df.iloc[0]['session_id'] == 'sess_test'
        assert df.iloc[0]['cohort'] == 'control'
    
    def test_control_constraints_applied(self):
        """Control cohort overrides min_chunks and disables parametric."""
        cohort_config = CohortConfig.apply_control_constraints(hybrid_config)
        assert cohort_config['rag_quality']['min_chunks'] == 3
        assert cohort_config['parametric_usage']['max_ratio'] == 0.0
    
    def test_experiment_duration_check(self):
        """Experiment only runs within configured duration."""
        # Set duration to 1 day in past
        config['experiments'][0]['duration_days'] = -1
        manager = ExperimentManager(config, project_root)
        assert not manager.should_run_experiment("hybrid_vs_pure_rag")
```

### 3.2 Unit Tests: `tests/test_device_detection.py` (~250 lines)

```python
class TestDeviceDetector:
    
    def test_detect_tandem_from_metadata(self):
        """Correctly identify Tandem pump from PDF title."""
        detector = DeviceDetector()
        # Create mock PDF with Tandem metadata
        result = detector.detect_from_pdf_metadata(tandem_pdf_path)
        assert result['pump'] == 'tandem_tslim'
        assert result['confidence'] >= 0.8
    
    def test_detect_dexcom_from_content(self):
        """Extract Dexcom G7 from PDF content."""
        detector = DeviceDetector()
        result = detector.detect_from_content_sample(dexcom_pdf_path)
        assert 'dexcom' in result['cgm']
        assert 'g7' in result['cgm']
    
    def test_fallback_filename_detection(self):
        """Fallback to filename if metadata missing."""
        detector = DeviceDetector()
        result = detector.detect_from_filename("OmnipodDash_UserGuide.pdf")
        assert result['pump'] == 'omnipod'
        assert result['confidence'] == 0.6
    
    def test_unknown_device_handled_gracefully(self):
        """Unknown device returns empty dict, not error."""
        detector = DeviceDetector()
        result = detector.detect_from_pdf_metadata(unknown_pdf_path)
        assert result == {}
    
    def test_device_profile_storage(self):
        """Device profile correctly serialized/deserialized."""
        profile = UserDeviceProfile(
            session_id='sess_test',
            pump='tandem_tslim',
            cgm='dexcom_g7',
            detection_confidence={'pump': 0.95, 'cgm': 0.88}
        )
        manager = UserDeviceManager(project_root)
        manager.save_profile(profile)
        
        loaded = manager.load_profile('sess_test')
        assert loaded.pump == 'tandem_tslim'
        assert loaded.cgm == 'dexcom_g7'
```

### 3.3 Unit Tests: `tests/test_device_personalization.py` (~200 lines)

```python
class TestPersonalizationManager:
    
    def test_confidence_boost_applied(self):
        """User's device chunks get +0.2 confidence."""
        manager = PersonalizationManager(config, project_root)
        
        # Create mock chunks: one tandem, one generic
        chunks = [
            SearchResult(quote="Tandem manual...", confidence=0.7, source='device_tandem_tslim'),
            SearchResult(quote="Generic...", confidence=0.75, source='guidelines'),
        ]
        
        # Set user device to Tandem
        manager.save_profile(UserDeviceProfile(..., pump='tandem_tslim'))
        
        boosted = manager.apply_device_boost(chunks, 'sess_test', config)
        
        # Tandem chunk should have +0.2
        tandem_chunk = [c for c in boosted if 'tandem' in c.source][0]
        generic_chunk = [c for c in boosted if 'guidelines' in c.source][0]
        
        assert tandem_chunk.confidence == 0.9  # 0.7 + 0.2
        assert generic_chunk.confidence == 0.75  # unchanged
    
    def test_boost_capped_at_max(self):
        """Boost never exceeds configured max."""
        manager = PersonalizationManager({...,'max_boost': 0.3}, project_root)
        
        chunks = [SearchResult(confidence=0.85, source='device_tandem_tslim')]
        boosted = manager.apply_device_boost(chunks, 'sess_test', config)
        
        # 0.85 + 0.3 = 1.15, but capped at 1.0
        assert boosted[0].confidence <= 1.0
    
    def test_feedback_learning_increases_boost(self):
        """Thumbs-up increases device boost."""
        manager = PersonalizationManager(config, project_root)
        
        initial = manager.get_current_boost('sess_test', 'device_tandem_tslim')
        manager.adjust_boost_from_feedback('sess_test', 'device_tandem_tslim', 'helpful')
        updated = manager.get_current_boost('sess_test', 'device_tandem_tslim')
        
        assert updated > initial
        assert updated - initial == 0.1  # learning_rate
    
    def test_feedback_learning_decreases_boost(self):
        """Thumbs-down decreases device boost."""
        manager = PersonalizationManager(config, project_root)
        
        # Pre-set some boost
        manager.save_adjustment_state(BoostAdjustmentState(
            session_id='sess_test',
            source_adjustments={'device_tandem_tslim': 0.25}
        ))
        
        manager.adjust_boost_from_feedback('sess_test', 'device_tandem_tslim', 'not-helpful')
        updated = manager.get_current_boost('sess_test', 'device_tandem_tslim')
        
        assert updated < 0.25
        assert 0.25 - updated == 0.1  # learning_rate
    
    def test_boost_never_negative(self):
        """Boost floors at 0.0."""
        manager = PersonalizationManager(config, project_root)
        
        manager.save_adjustment_state(BoostAdjustmentState(
            session_id='sess_test',
            source_adjustments={'device_tandem_tslim': 0.05}
        ))
        
        # Multiple negative feedback events
        for _ in range(10):
            manager.adjust_boost_from_feedback('sess_test', 'device_tandem_tslim', 'not-helpful')
        
        final = manager.get_current_boost('sess_test', 'device_tandem_tslim')
        assert final >= 0.0
```

### 3.4 Integration Tests: `tests/test_experimentation_integration.py` (~300 lines)

```python
class TestExperimentationIntegration:
    
    def test_control_vs_treatment_different_responses(self):
        """Same query returns different knowledge_breakdown in control vs treatment."""
        agent = UnifiedAgent(project_root)
        query = "How do I change my basal rates?"
        
        # Get control response
        control_response = list(agent.query_stream(query, session_id='control_user'))
        control_text = ''.join(control_response)
        
        # Get treatment response
        treatment_response = list(agent.query_stream(query, session_id='treatment_user'))
        treatment_text = ''.join(treatment_response)
        
        # Responses should differ due to different parametric usage
        assert control_text != treatment_text
        # Or at least have different parametric ratios in metadata
    
    def test_device_boost_improves_ranking(self):
        """User's device chunks ranked higher after boost applied."""
        agent = UnifiedAgent(project_root, enable_personalization=True)
        
        # Set user device
        manager = agent.personalization_manager
        manager.save_profile(UserDeviceProfile(
            session_id='device_test',
            pump='tandem_tslim',
            cgm='dexcom_g7'
        ))
        
        # Query and verify Tandem chunks rank highest
        query = "How do I calculate insulin?"
        results = agent.researcher.query_knowledge(
            query,
            session_id='device_test'
        )
        
        # First result should preferentially be from user's device
        # (Tandem for pump/Dexcom for CGM questions)
        first_source = results[0].source
        assert 'tandem' in first_source.lower() or 'dexcom' in first_source.lower()
    
    def test_feedback_loop_adjustment_persists(self):
        """Feedback adjustments saved across sessions."""
        manager = PersonalizationManager(config, project_root)
        
        # Session 1: Mark device source as helpful
        manager.adjust_boost_from_feedback('sess_1', 'device_tandem_tslim', 'helpful')
        
        # Session 2: Load same device profile
        boost_after = manager.get_current_boost('sess_1', 'device_tandem_tslim')
        
        assert boost_after > 0.2  # Base + feedback adjustment
    
    def test_ab_test_assignment_logged_with_response(self):
        """A/B test cohort and metadata included in response."""
        agent = UnifiedAgent(project_root, enable_experimentation=True)
        
        response = agent.query_stream("test query", session_id='sess_test')
        response_text = ''.join(response)
        
        # Check assignments CSV was updated
        csv_path = Path('data/analysis/ab_test_assignments.csv')
        assert csv_path.exists()
        
        df = pd.read_csv(csv_path)
        test_row = df[df['session_id'] == 'sess_test'].iloc[-1]
        
        assert test_row['cohort'] in ['control', 'treatment']
        assert test_row['query'] == "test query"
```

---

## 4. INTEGRATION POINTS & DEPENDENCIES

### 4.1 Session Management
- **Current state:** `session_id` likely from web frontend (cookies/localStorage)
- **Needed:** Ensure `session_id` passed to `unified_agent.query_stream()`
- **Files affected:** `web/app.py` (route handler), JavaScript frontend

### 4.2 Feedback Logging
- **Current state:** Feedback written to CSV in `/api/feedback` endpoint
- **Needed:** Add cohort and response time to feedback CSV
- **Files affected:** `web/app.py` (feedback route), response metadata

### 4.3 ChromaDB Collection Organization
- **Current state:** PDFs scanned from `docs/manuals/hardware`, `docs/user-sources`, etc.
- **Needed:** Ensure device-specific PDFs organized by device type
  - Example: `docs/user-sources/devices/tandem_tslim/` → `device_tandem_tslim` collection
- **Files affected:** `agents/researcher_chromadb.py` (collection naming)

### 4.4 Configuration Loading
- **Current state:** `hybrid_knowledge.yaml` loaded in multiple places
- **Needed:** Ensure `ExperimentManager` and `PersonalizationManager` both load config
- **Implementation:** Pass config dict to managers, validate at initialization

---

## 5. IMPLEMENTATION SEQUENCING (12 DAYS)

### Phase 1: Core Infrastructure (Days 1-2)
1. Create `agents/experimentation.py` with `ExperimentManager` + session anonymization ⭐ Refinement 1
2. Create `agents/device_detection.py` with `DeviceDetector`
3. Update `config/hybrid_knowledge.yaml` with new sections (min_sample_size=620, decay_factor) ⭐ Refinements 3, 4
4. Write unit tests for both modules

**Checkpoint:** 
- [ ] Cohort assignment deterministic
- [ ] Session ID anonymization working
- [ ] Device detection accuracy > 85%

### Phase 2: Integration with Unified Agent (Days 3-4)
1. Modify `agents/unified_agent.py` to inject managers
2. Modify `agents/researcher_chromadb.py` to accept session_id
3. Update query flow with cohort constraints
4. Update response metadata to include cohort
5. Implement statistical power analysis documentation ⭐ Refinement 3

**Checkpoint:** 
- [ ] Run 20 sample queries in both cohorts
- [ ] Verify parametric_ratio=0% in control
- [ ] Verify parametric_ratio>30% in treatment

### Phase 3: Personalization + Regularization (Days 5-6)
1. Create `agents/device_personalization.py` with `PersonalizationManager` + regularized learning ⭐ Refinement 4
2. Integrate into `researcher_chromadb.py` for confidence boost
3. Implement decaying learning rate formula
4. Write unit tests for personalization with feedback count tracking

**Checkpoint:**
- [ ] Device boost applied correctly (+0.2)
- [ ] Feedback learning rate decays with count
- [ ] Boost never exceeds 1.0 or goes below 0.0

### Phase 4: Analytics & Frontend (Days 7-8)
1. Enhance `/api/feedback-stats` endpoint with cohort breakdown
2. Add GET `/api/experiments/status` dashboard endpoint ⭐ Refinement 5
3. Add POST `/api/devices/override` for manual corrections ⭐ Refinement 2
4. Update feedback logging to include: cohort, response_time_ms, parametric_ratio
5. Add scipy for statistical calculations (add to requirements.txt)

**Checkpoint:**
- [ ] `/api/experiments/status` returns live statistics
- [ ] `/api/devices/override` accepts corrections
- [ ] Feedback CSV has all required columns
- [ ] Statistical significance calculated correctly (p-value, t-statistic, Cohen's d)

### Phase 5: Device Confirmation UI + Documentation (Days 9-10)
1. Create frontend UI for device detection confirmation
   - Show detected devices with confidence scores
   - "Confirm" button → accept auto-detection
   - "Edit" button → POST to /api/devices/override ⭐ Refinement 2
2. Create `docs/EXPERIMENTATION.md` with:
   - Statistical power analysis calculator (min_sample_size formula)
   - Success criteria for declaring winner
   - Troubleshooting guide
3. Write integration tests in `tests/test_experimentation_integration.py`

**Checkpoint:**
- [ ] Device confirmation UI works end-to-end
- [ ] Manual override rate < 20% (indicates good detection)
- [ ] Documentation complete and accurate

### Phase 6: User Acceptance Testing (Days 11-12)
1. Deploy to staging environment
2. Run 3-5 beta testers through complete flow:
   - Upload device PDFs
   - Confirm/correct device detection
   - Get responses in assigned cohort
   - Provide feedback
3. Verify A/B test dashboard shows live progress
4. Verify anonymization doesn't break anything
5. Final production readiness check

**Checkpoint:**
- [ ] All acceptance criteria met
- [ ] No privacy/GDPR violations
- [ ] Statistical rigor verified
- [ ] Team comfortable with decision criteria

---

## 6. VALIDATION CHECKLIST (30+ ITEMS)

### Refinement 1: Session ID Anonymization ⭐
- [ ] `anonymize_session_id()` function returns SHA-256 hash
- [ ] Same session_id always produces same hash (deterministic)
- [ ] All CSV files use session_id_hash, not raw session_id
- [ ] All JSON files use session_id_hash in directory names
- [ ] No plaintext session IDs in logs
- [ ] GDPR/HIPAA compliance verified

### Refinement 2: Device Detection Manual Override ⭐
- [ ] Frontend UI shows detected devices with confidence %
- [ ] "Confirm" button accepts auto-detection
- [ ] "Edit" button opens device selector modal
- [ ] POST /api/devices/override endpoint works
- [ ] User corrections saved with override_source='user'
- [ ] Manual override rate < 20%

### Refinement 3: Statistical Power Analysis ⭐
- [ ] min_sample_size = 620 (calculated for 5% effect at 80% power)
- [ ] Formula documented: n ≈ 2 * ((z_α/2 + z_β) / effect_size)² * p*(1-p)
- [ ] For baseline=70%, target=75%, α=0.05, power=0.80
- [ ] 30-day experiment can reach 620 per cohort
- [ ] Winner only declared after min_sample_size reached

### Refinement 4: Feedback Loop Regularization ⭐
- [ ] Decaying learning rate: 0.1 / (1 + 0.1 * feedback_count)
- [ ] feedback_count tracked in BoostAdjustmentState
- [ ] After 5 feedbacks: rate ≈ 0.067
- [ ] After 10 feedbacks: rate ≈ 0.050
- [ ] Boost stabilizes (doesn't oscillate)
- [ ] Single negative feedback doesn't destroy boost

### Refinement 5: Experiment Dashboard Endpoint ⭐
- [ ] GET /api/experiments/status returns live statistics
- [ ] Shows: n per cohort, helpful_rate, response_time, p_value
- [ ] Includes: t-statistic, Cohen's d, effect size
- [ ] min_sample_size_reached flag accurate
- [ ] Winner shows 'treatment', 'control', or None
- [ ] Recommendation text actionable

### Experimentation Framework
- [ ] Cohort assignment deterministic
- [ ] Cohort split balanced (~50/50 over 1000 sessions)
- [ ] Control cohort disables parametric (spot-check 10 queries)
- [ ] Treatment cohort uses hybrid (spot-check 10 queries)
- [ ] Assignments logged to CSV with timestamps

### Device Personalization
- [ ] Device detection works for all 8 pump types
- [ ] Device detection works for all 3 CGM types
- [ ] PDF metadata extraction robust (>80% success)
- [ ] Fallback to filename works
- [ ] Fallback to content sampling works
- [ ] Unknown devices handled gracefully
- [ ] Device profiles stored correctly
- [ ] Confidence boost applied (+0.2)
- [ ] Boost never exceeds 1.0
- [ ] Boost never below 0.0

### Integration
- [ ] Session IDs properly tracked end-to-end
- [ ] Response metadata includes cohort + boost
- [ ] Feedback CSV has all columns
- [ ] No performance regression (p95 < 3 seconds)
- [ ] All existing 42 tests pass
- [ ] New tests have 80%+ coverage
- [ ] Privacy/security verified

---

## 7. RISK MITIGATION

| Risk | Impact | Mitigation | Refinement |
|------|--------|-----------|-----------|
| Session ID privacy leak | GDPR/HIPAA violation | Hash all session IDs with SHA-256 before storage | #1 |
| Device detection false positives | User distrust | Manual override UI with confidence scores | #2 |
| Insufficient statistical power | Type II error (false negative) | Use 620 samples per cohort (80% power) | #3 |
| Feedback loop overfitting | Winner declared incorrectly | Regularize learning rate with decay formula | #4 |
| No operational visibility | Team can't decide to stop test | Dashboard endpoint shows live progress | #5 |
| Session ID not tracked consistently | Cohorts randomly reassigned | Add session ID validation, log warnings | - |
| Performance impact | Slow queries | Cache device profiles, lazy-load personalization | - |

---

## 8. SUCCESS CRITERIA FOR DECLARING WINNER (After 30 Days)

**ALL criteria must be met:**

1. **Sample Size:** ≥ 620 per cohort (control + treatment)
2. **Statistical Significance:** p-value < 0.05 (two-tailed t-test)
3. **Effect Size:** Helpful rate improvement ≥ 5% absolute (e.g., 70% → 75%)
   - Measured using Cohen's d (d ≥ 0.2 considered meaningful)
4. **Performance:** p95 response time < 3 seconds for both cohorts
   - Treatment acceptable ≤ control + 200ms
5. **User Satisfaction:** Qualitative feedback from beta testers confirms reduced friction

**If all criteria met:**
- ✅ Roll out winner (treatment hybrid) to 100% of users
- ✅ Sunset losing cohort (control pure RAG)
- ✅ Document results and publish findings

**If criteria NOT met:**
- ❌ Continue test (if still within 30 days)
- ❌ Extend duration if approaching min_sample_size
- ❌ Or declare no winner and maintain status quo

---

## 9. MONITORING & SUCCESS METRICS

### Primary Hypothesis: "Hybrid reduces friction"
- **Metric:** % helpful feedback (treatment > control)
- **Target:** Treatment ≥ 75% helpful rate (5% absolute improvement)
- **Acceptable variance:** ±3% (due to randomness)

### Secondary Metrics
- Response time: treatment acceptable ≤ control + 200ms
- Parametric ratio: treatment > 30%, control = 0%
- User satisfaction: qualitative feedback confirms reduced uncertainty

### Device Personalization Success
- **Metric:** Boost adjustment converges toward user preference
- **Indicator:** Device sources rank in top 2 for device-specific queries
- **Quality:** Manual override rate < 20% indicates good auto-detection

---

---

## 10. KNOWN LIMITATIONS & FUTURE WORK

1. **Session persistence:** Current approach assumes session_id from web frontend
   - Future: Implement server-side session store if needed

2. **Device detection coverage:** 8 manufacturers supported, extensible
   - Future: Add more manufacturers based on user uploads

3. **Statistical power:** 30-day experiments may need longer for rare queries
   - Future: Implement adaptive duration based on sample size

4. **Personalization cold start:** No boost for new users
   - Future: Implement collaborative filtering across similar device users

5. **Feedback delay:** Assumes feedback logged immediately after response
   - Future: Async feedback collection with time windows

---

## 11. CONSTRAINTS & REQUIREMENTS

**Mandatory (non-negotiable):**
- [ ] All existing 42 tests must pass
- [ ] No breaking changes to existing API contracts
- [ ] Session ID anonymization required (GDPR/HIPAA)
- [ ] Statistical power: min_sample_size = 620
- [ ] Feedback regularization required (prevent overfitting)
- [ ] Manual device override UI required (user control)
- [ ] Dashboard endpoint required (operational transparency)

**Dependencies (add to requirements.txt):**
- scipy ≥ 1.0 (for statistical tests)
- PyPDF2 (already used, ensure current version)

**File Organization (new directories to create):**
- `data/users/` (per-session data with hashed session IDs)
- `data/analysis/` (experiment assignments + feedback)

**API Contracts (don't break):**
- `/api/query` endpoint must accept session_id parameter
- Response metadata must preserve existing fields
- Feedback CSV must extend (not replace) existing columns

**Environmental Requirements:**
- Web frontend must pass session_id to backend in all requests
- Device-specific PDFs should be organized by type (docs/user-sources/devices/)
- ChromaDB collections named device_{manufacturer}_{model}

---

## 12. DELIVERABLE SUMMARY

| File | Type | New/Modified | Lines | Refinements |
|------|------|--------------|-------|------------|
| `agents/experimentation.py` | New | New | 450-550 | #1 (anonymization) |
| `agents/device_detection.py` | New | New | 400-500 | #2 (override) |
| `agents/device_personalization.py` | New | New | 350-450 | #4 (regularization) |
| `agents/unified_agent.py` | Modified | Modified | +50 | - |
| `agents/researcher_chromadb.py` | Modified | Modified | +60-80 | - |
| `web/app.py` | Modified | Modified | +150-200 | #2, #5 (endpoints) |
| `config/hybrid_knowledge.yaml` | Modified | Modified | +40 | #3, #4 (configs) |
| `docs/EXPERIMENTATION.md` | New | New | 600-900 | #3 (power analysis) |
| `tests/test_experimentation.py` | New | New | ~300 | #1, #3, #5 |
| `tests/test_device_detection.py` | New | New | ~300 | #2 |
| `tests/test_device_personalization.py` | New | New | ~250 | #4 |
| `tests/test_experimentation_integration.py` | New | New | ~350 | All |

**Total new code:** ~3,000-4,000 lines (tests + implementation)  
**Implementation duration:** 12 days (6 phases)  
**Privacy compliance:** GDPR Article 25 (data protection by design)  
**Statistical rigor:** 80% power for 5% effect at α=0.05  
**User agency:** Manual override for all device detections

---

## SUMMARY OF REFINEMENTS

| # | Name | Problem | Solution | Impact |
|---|------|---------|----------|--------|
| 1 | Session Anonymization | PII in plaintext (GDPR/HIPAA violation) | SHA-256 hash all session IDs before storage | Privacy compliance, user trust |
| 2 | Device Override UI | Auto-detection can be wrong, users lose trust | Show confidence scores, allow manual correction | User agency, transparency, quality metrics |
| 3 | Statistical Power | min_sample_size=100 too low (only 30% power) | Use 620 per cohort (80% power for 5% effect) | Valid conclusions, avoid false negatives |
| 4 | Feedback Regularization | Single noisy feedback destroys good boost | Decaying learning rate (effective_rate = 0.1 / (1 + 0.1 * count)) | Stable personalization, convergence |
| 5 | Dashboard Endpoint | No operational visibility, can't decide when to stop | GET /api/experiments/status with live stats | Transparency, actionable decisions |

---

## NEXT STEPS

**The comprehensive implementation plan is ready.**

**When ready to proceed:**

1. **Review and validate** this plan with team
2. **Confirm all 5 refinements** are acceptable
3. **Proceed with Phase 1** (Core Infrastructure, Days 1-2)
   - Create experimentation.py with anonymization
   - Create device_detection.py
   - Update config/hybrid_knowledge.yaml
   - Write unit tests
   - Checkpoint validation

4. **Follow sequential phases** (2-6) maintaining checkpoints
5. **Deliver incrementally** with testing at each phase
6. **Validate success criteria** before Phase 6 UAT

**Not to execute until approved.**

---

## DELIVERABLE SUMMARY

| File | Type | New/Modified | Lines | Status |
|------|------|--------------|-------|--------|
| `agents/experimentation.py` | New | New | 400-500 | Plan complete |
| `agents/device_detection.py` | New | New | 350-450 | Plan complete |
| `agents/device_personalization.py` | New | New | 300-400 | Plan complete |
| `agents/unified_agent.py` | Modified | Modified | +50 | Plan complete |
| `agents/researcher_chromadb.py` | Modified | Modified | +60-80 | Plan complete |
| `web/app.py` | Modified | Modified | +80-120 | Plan complete |
| `config/hybrid_knowledge.yaml` | Modified | Modified | +30 | Plan complete |
| `docs/EXPERIMENTATION.md` | New | New | 500-800 | Plan complete |
| `tests/test_experimentation.py` | New | New | ~300 | Plan complete |
| `tests/test_device_detection.py` | New | New | ~250 | Plan complete |
| `tests/test_device_personalization.py` | New | New | ~200 | Plan complete |
| `tests/test_experimentation_integration.py` | New | New | ~300 | Plan complete |

**Total new code:** ~2,500-3,500 lines (tests + implementation)

