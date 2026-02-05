# A/B Testing & Device Personalization - REFINED IMPLEMENTATION PLAN

**Status:** ✅ Detailed Plan Complete (1,714 lines)  
**Date:** February 2, 2026  
**Ready for:** Team review and approval before execution

---

## 5 CRITICAL REFINEMENTS APPLIED

### 1. 🔒 Session ID Anonymization (Privacy Compliance)
**Problem:** Session IDs are PII; storing plaintext violates GDPR/HIPAA  
**Solution:** SHA-256 hash all session IDs before storage (deterministic, one-way)  
**Impact:** GDPR Article 25 compliance, user trust, no privacy violations  
**Implementation:** `ExperimentManager.anonymize_session_id()` in agents/experimentation.py

### 2. 👥 Device Override UI (User Agency & Transparency)
**Problem:** Auto-detection can be wrong; users lose trust in system  
**Solution:** Show detected devices with confidence scores; allow manual corrections  
**Impact:** User control, transparency, quality feedback for algorithm improvement  
**Implementation:** Frontend UI + POST `/api/devices/override` endpoint  
**Success metric:** Manual override rate < 20%

### 3. 📊 Statistical Power Analysis (Rigorous Science)
**Problem:** min_sample_size=100 only provides ~30% power (high Type II error risk)  
**Solution:** Use 620 per cohort (80% power for 5% effect at α=0.05)  
**Impact:** Valid conclusions, avoid false negatives, credible results  
**Formula:** n ≈ 2 * ((z_α/2 + z_β) / effect_size)² * p*(1-p)  
**Implementation:** Config: `min_sample_size: 620`

### 4. 📉 Feedback Regularization (Stable Personalization)
**Problem:** Single negative feedback event destroys good device boost  
**Solution:** Decaying learning rate based on feedback count  
**Formula:** `effective_rate = 0.1 / (1 + 0.1 * feedback_count)`  
**Impact:** Boost stabilizes after 5-10 feedback events, prevents overfitting  
**Implementation:** `calculate_effective_learning_rate()` in agents/device_personalization.py

### 5. 📈 Experiment Dashboard (Operational Transparency)
**Problem:** No real-time view of A/B test progress; can't decide when to stop  
**Solution:** GET `/api/experiments/status` showing live cohort statistics  
**Data:** Merges assignments.csv + feedback.csv for real-time analysis  
**Output:** p-value, t-statistic, Cohen's d, effect size, recommendation  
**Impact:** Team can transparently monitor progress and declare winners  
**Implementation:** New endpoint in web/app.py

---

## SCOPE SUMMARY

### New Modules (5)
- `agents/experimentation.py` (450-550 lines) - Cohort assignment + session anonymization
- `agents/device_detection.py` (400-500 lines) - Manufacturer detection + profiles
- `agents/device_personalization.py` (350-450 lines) - Confidence boost + regularized learning
- `docs/EXPERIMENTATION.md` (600-900 lines) - Power analysis, success criteria, troubleshooting
- `web/app.py` additions (150-200 lines) - Dashboard + override endpoints

### Modified Modules (3)
- `agents/unified_agent.py` (+50 lines) - Manager injection, cohort constraints
- `agents/researcher_chromadb.py` (+60-80 lines) - Device boost integration
- `config/hybrid_knowledge.yaml` (+40 lines) - New sections with power analysis parameters

### Test Suite (4 new files)
- `tests/test_experimentation.py` (~300 lines) - Anonymization, cohorts, constraints
- `tests/test_device_detection.py` (~300 lines) - Detection accuracy, fallbacks, storage
- `tests/test_device_personalization.py` (~250 lines) - Boost application, feedback learning
- `tests/test_experimentation_integration.py` (~350 lines) - End-to-end flows

**Total:** ~3,000-4,000 lines of implementation + tests

---

## IMPLEMENTATION PHASES (12 DAYS)

| Phase | Duration | Key Tasks | Checkpoint |
|-------|----------|-----------|-----------|
| 1: Core Infrastructure | Days 1-2 | experimentation.py, device_detection.py, config, unit tests | Cohort assignment deterministic, device detection >85% |
| 2: Unified Agent Integration | Days 3-4 | Inject managers, cohort constraints, power analysis doc | 20 test queries: control has 0% parametric, treatment >30% |
| 3: Personalization + Learning | Days 5-6 | device_personalization.py, regularized feedback, unit tests | Device boost +0.2 applied, learning rate decays with count |
| 4: Analytics & Endpoints | Days 7-8 | Dashboard endpoint, device override, feedback logging, scipy | `/api/experiments/status` returns live stats with p-value |
| 5: Device UI + Docs | Days 9-10 | Frontend confirmation UI, EXPERIMENTATION.md, integration tests | UI works, documentation complete, manual override <20% |
| 6: User Acceptance Test | Days 11-12 | Deploy to staging, beta test flow, final validation | All success criteria verified, production ready |

---

## SUCCESS CRITERIA FOR DECLARING WINNER (After 30 Days)

**ALL must be met:**
1. ✅ Sample Size: ≥ 620 per cohort
2. ✅ Significance: p-value < 0.05
3. ✅ Effect Size: ≥ 5% absolute improvement (70% → 75%)
4. ✅ Performance: p95 < 3 seconds
5. ✅ User Satisfaction: Qualitative confirmation

**If all met:** Roll out treatment (hybrid) to 100%  
**If not:** Continue test or declare no winner

---

## KEY METRICS TO MONITOR

### Primary (Hypothesis Test)
- **% Helpful Feedback:** Treatment target ≥ 75% (baseline ~70%)
- **Threshold:** 5% absolute improvement required for win

### Secondary
- **Response Time:** Treatment ≤ control + 200ms
- **Parametric Ratio:** Treatment > 30%, control = 0%
- **Device Personalization:** Device sources in top 2 for device-specific queries

### Quality
- **Manual Override Rate:** < 20% (indicates good auto-detection)
- **Learning Convergence:** Boost stabilizes after 5-10 feedback events

---

## VALIDATION CHECKLIST (30+ ITEMS)

By component:
- **Refinement 1 (Anonymization):** 6 items
- **Refinement 2 (Override UI):** 6 items
- **Refinement 3 (Power):** 5 items
- **Refinement 4 (Regularization):** 6 items
- **Refinement 5 (Dashboard):** 6 items
- **Original Requirements:** 20+ items

---

## CONSTRAINTS (NON-NEGOTIABLE)

- ✅ All existing 42 tests must pass
- ✅ No API contract breaks
- ✅ Session anonymization mandatory (GDPR)
- ✅ min_sample_size = 620 (statistical rigor)
- ✅ Feedback regularization required (prevent overfitting)
- ✅ Manual override UI required (user control)
- ✅ Dashboard endpoint required (transparency)

---

## DEPENDENCIES

**Python packages (add to requirements.txt):**
- scipy ≥ 1.0 (t-test, statistical analysis)
- PyPDF2 (already present, ensure current)

**Infrastructure:**
- `data/users/` directory for per-session data (hashed session IDs)
- `data/analysis/` directory for experiment assignments + feedback
- Device-specific PDF organization (docs/user-sources/devices/)
- ChromaDB collections: device_{manufacturer}_{model}

**Frontend requirement:**
- Must pass session_id to backend with every request
- Must show device confirmation UI after PDF upload

---

## COMPLIANCE & STANDARDS

✅ **GDPR Article 25** (Privacy by Design): Session anonymization  
✅ **HIPAA** (Protected Health Information): No plaintext PII storage  
✅ **Statistical Rigor** (Type I & II errors): Power analysis, minimum sample size  
✅ **Transparency** (Operationalization): Dashboard endpoint shows live progress  
✅ **User Agency** (Control): Manual override for all device detections

---

## RISK MITIGATION MATRIX

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|-----------|--------|
| Session ID privacy leak | High | Critical | SHA-256 anonymization (#1) | ✅ Covered |
| Device detection false positives | Medium | Medium | Manual override UI (#2) | ✅ Covered |
| Statistical false negative | Medium | Critical | 620 sample size (#3) | ✅ Covered |
| Feedback loop instability | Medium | Medium | Regularization (#4) | ✅ Covered |
| No operational visibility | Low | Medium | Dashboard (#5) | ✅ Covered |

---

## WHAT'S NEXT

**Current Status:** Detailed plan complete and ready for review  
**Document:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (1,714 lines)

**To proceed:**
1. Review and validate all 5 refinements
2. Confirm team alignment on success criteria
3. Schedule 12-day implementation window
4. Assign resources for 6 phases
5. Execute Phase 1 (Days 1-2) and validate checkpoint

**Estimated Effort:**
- Implementation: 8 days (full-time developer)
- Testing: 3 days (overlap + UAT)
- Documentation: 1 day
- Total: 12 days (sequential phases)

**No execution until approved.**

---

## DOCUMENT REFERENCE

Full detailed plan available in: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

Sections included:
- ✅ 2 Conceptual Architecture Flows
- ✅ 5 Critical Refinements Explained (with rationale)
- ✅ 3 Core Modules (experimentation, device_detection, device_personalization)
- ✅ 3 Modified Modules (unified_agent, researcher_chromadb, web/app)
- ✅ Configuration additions (YAML with power analysis parameters)
- ✅ Dashboard endpoints specification
- ✅ 6-phase implementation sequencing
- ✅ 30+ point validation checklist
- ✅ Risk mitigation matrix
- ✅ Success criteria framework
- ✅ Monitoring & metrics
- ✅ Known limitations & future work
- ✅ Constraints & requirements matrix
- ✅ Deliverable summary table

