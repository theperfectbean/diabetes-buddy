# Hybrid Knowledge System Test Plan

## Overview
Comprehensive test suite for the two-stage RAG + parametric knowledge system in Diabetes Buddy.

---

## 1. Unit Tests: `tests/test_hybrid_knowledge.py`

### 1.1 RAG Quality Assessment Tests

| Test Case | Input | Expected Output | Priority |
|-----------|-------|-----------------|----------|
| `test_rag_quality_sufficient_chunks` | 5 chunks, avg_confidence=0.85 | `is_sufficient=True`, `topic_coverage='sufficient'` | High |
| `test_rag_quality_insufficient_chunks` | 2 chunks, avg_confidence=0.9 | `is_sufficient=False`, `topic_coverage='sparse'` | High |
| `test_rag_quality_low_confidence` | 4 chunks, avg_confidence=0.5 | `is_sufficient=False`, `topic_coverage='partial'` | High |
| `test_rag_quality_boundary_3_chunks` | 3 chunks, avg_confidence=0.7 | `is_sufficient=True` (boundary case) | Medium |
| `test_rag_quality_boundary_confidence` | 3 chunks, avg_confidence=0.69 | `is_sufficient=False` (just below) | Medium |
| `test_rag_quality_empty_results` | 0 chunks | `is_sufficient=False`, `topic_coverage='sparse'` | High |
| `test_rag_quality_source_diversity` | chunks from 3 different sources | `source_diversity=3` | Medium |
| `test_rag_quality_single_source` | chunks from 1 source | `source_diversity=1` | Low |

### 1.2 Knowledge Breakdown Calculation Tests

| Test Case | Input | Expected Output | Priority |
|-----------|-------|-----------------|----------|
| `test_breakdown_rag_only` | RAG sufficient, no parametric | `rag_ratio=1.0`, `parametric_ratio=0.0`, `primary_source_type='rag'` | High |
| `test_breakdown_hybrid_mode` | RAG insufficient (2 chunks, 0.6 conf) | `rag_ratio=0.4`, `parametric_ratio=0.6`, `primary_source_type='hybrid'` | High |
| `test_breakdown_parametric_heavy` | RAG very sparse (1 chunk, 0.3 conf) | `parametric_ratio > 0.7`, `primary_source_type='parametric'` | High |
| `test_breakdown_glooko_present` | Glooko data + RAG | `primary_source_type='glooko'` takes precedence | Medium |
| `test_breakdown_blended_confidence` | RAG conf=0.8, parametric=0.6, 50/50 split | `blended_confidence=0.7` | Medium |
| `test_breakdown_parametric_fixed_confidence` | Any parametric use | `parametric_confidence=0.6` (fixed) | Low |

### 1.3 Hybrid Prompt Building Tests

| Test Case | Input | Expected Output | Priority |
|-----------|-------|-----------------|----------|
| `test_hybrid_prompt_contains_rag_context` | RAG chunks present | Prompt includes RAG context section | High |
| `test_hybrid_prompt_attribution_instructions` | Any hybrid prompt | Contains "[General medical knowledge]" instruction | High |
| `test_hybrid_prompt_prohibition_rules` | Any hybrid prompt | Contains dosing prohibition, device-specific prohibition | High |
| `test_hybrid_prompt_priority_order` | Mixed sources | States RAG priority > parametric | Medium |
| `test_hybrid_prompt_with_glooko` | Glooko data present | Includes Glooko context section | Medium |

### 1.4 UnifiedResponse Generation Tests

| Test Case | Input | Expected Output | Priority |
|-----------|-------|-----------------|----------|
| `test_response_rag_sufficient` | Good RAG results | `requires_enhanced_safety_check=False` | High |
| `test_response_hybrid_mode` | Sparse RAG | `requires_enhanced_safety_check=True`, `sources_used=['rag', 'parametric']` | High |
| `test_response_disclaimer_parametric_heavy` | `parametric_ratio > 0.5` | Disclaimer includes parametric warning | High |
| `test_response_disclaimer_rag_only` | RAG only | Standard disclaimer without parametric warning | Medium |
| `test_response_success_false_on_error` | LLM error | `success=False` | Medium |

---

## 2. Integration Tests: `tests/test_e2e_hybrid.py`

### 2.1 End-to-End Query Flow Tests

| Test Case | Query | RAG Mock | Expected Behavior | Priority |
|-----------|-------|----------|-------------------|----------|
| `test_e2e_insulin_timing_sufficient_rag` | "When should I take insulin before meals?" | 4 chunks, conf=0.85 | Pure RAG response, no parametric markers | High |
| `test_e2e_insulin_timing_sparse_rag` | "When should I take insulin before meals?" | 1 chunk, conf=0.4 | Hybrid response with attribution markers | High |
| `test_e2e_general_diabetes_question` | "What is type 2 diabetes?" | 5 chunks, conf=0.9 | RAG-only, evidence-based badge | High |
| `test_e2e_obscure_topic` | "What is honeymoon phase in T1D?" | 0 chunks | Parametric-heavy response with appropriate warnings | High |
| `test_e2e_device_query_with_rag` | "How do I calibrate Dexcom G6?" | 3 chunks from device docs | RAG-only, no parametric for devices | High |
| `test_e2e_device_query_no_rag` | "How do I use XYZ unknown pump?" | 0 chunks | Safety block, refuses parametric for unknown devices | High |
| `test_e2e_glooko_personal_data` | "What was my average glucose last week?" | Glooko data present | Personal data badge, Glooko prioritized | Medium |
| `test_e2e_emergency_query` | "I'm having severe hypoglycemia" | Any | Emergency response, safety first | Critical |

### 2.2 Web API Integration Tests

| Test Case | Endpoint | Request | Expected Response | Priority |
|-----------|----------|---------|-------------------|----------|
| `test_api_unified_query_rag_response` | POST `/api/query/unified` | Standard query | `knowledge_breakdown` present, `primary_source_type` set | High |
| `test_api_unified_query_hybrid_response` | POST `/api/query/unified` | Query triggering hybrid | `knowledge_breakdown.parametric_ratio > 0` | High |
| `test_api_feedback_endpoint` | POST `/api/feedback` | `{message_id, helpful: true}` | 200 OK, logged to CSV | Medium |
| `test_api_feedback_invalid` | POST `/api/feedback` | Missing fields | 422 Validation Error | Low |
| `test_api_response_time_under_threshold` | POST `/api/query/unified` | Any | Response < 5 seconds | Medium |

---

## 3. Safety Tests: `tests/test_safety_hybrid.py`

### 3.1 Hybrid Audit Function Tests

| Test Case | Response Content | Expected Audit Result | Priority |
|-----------|------------------|----------------------|----------|
| `test_audit_hybrid_parametric_markers_detected` | Contains "[General medical knowledge]" | `parametric_claims` populated | High |
| `test_audit_hybrid_no_parametric_markers` | Pure RAG response | `parametric_claims=[]`, `parametric_ratio=0.0` | High |
| `test_audit_hybrid_rag_citations_found` | Contains "According to ADA guidelines..." | `rag_citations_found=True` | High |
| `test_audit_hybrid_missing_citations` | Parametric claims without citations | `hybrid_safety_checks_passed=False` | High |

### 3.2 Dosing Safety Tests

| Test Case | Response Content | Expected Result | Priority |
|-----------|------------------|-----------------|----------|
| `test_audit_parametric_dosing_blocked` | "Take 10 units [General medical knowledge]" | `is_safe=False`, dosing violation | Critical |
| `test_audit_rag_dosing_allowed` | "ADA recommends starting at 0.1 units/kg [Source: ADA]" | `is_safe=True` | High |
| `test_audit_dosing_patterns_comprehensive` | Various dosing patterns | All blocked when parametric | High |
| `test_audit_dosing_units_pattern` | "inject X units" variations | Detected as dosing advice | Medium |
| `test_audit_dosing_percentage_pattern` | "increase by 10%" variations | Detected as dosing advice | Medium |

### 3.3 Device Query Safety Tests

| Test Case | Query | RAG Available | Expected Result | Priority |
|-----------|-------|---------------|-----------------|----------|
| `test_audit_device_query_with_rag` | "Omnipod settings" | Yes | `is_safe=True` | High |
| `test_audit_device_query_no_rag` | "Unknown pump XYZ setup" | No | `is_safe=False`, `inappropriate_parametric_use=True` | High |
| `test_audit_device_detection_patterns` | Various device names | N/A | `is_device_query=True` | Medium |
| `test_audit_device_cgm_patterns` | CGM-related queries | N/A | `is_device_query=True` | Medium |
| `test_audit_device_pump_patterns` | Pump-related queries | N/A | `is_device_query=True` | Medium |

### 3.4 Citation Enforcement Tests

| Test Case | Response Content | Expected Result | Priority |
|-----------|------------------|-----------------|----------|
| `test_audit_citation_required_when_parametric` | Parametric claims, no RAG citations | Warning flag set | High |
| `test_audit_citation_patterns_recognized` | "According to...", "Based on guidelines..." | `rag_citations_found=True` | Medium |
| `test_audit_citation_mixed_response` | Both RAG and parametric properly attributed | `hybrid_safety_checks_passed=True` | High |

### 3.5 Parametric Ratio Calculation Tests

| Test Case | Response Content | Expected Ratio | Priority |
|-----------|------------------|----------------|----------|
| `test_calculate_ratio_all_parametric` | All sentences have markers | `ratio ≈ 1.0` | Medium |
| `test_calculate_ratio_no_parametric` | No markers | `ratio = 0.0` | Medium |
| `test_calculate_ratio_mixed` | 2/4 sentences parametric | `ratio ≈ 0.5` | Medium |

---

## 4. Pytest Fixture Structure

```python
# tests/conftest.py additions

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional

# ============================================
# RAG Mock Fixtures
# ============================================

@pytest.fixture
def mock_rag_sufficient():
    """Mock RAG results with sufficient coverage (≥3 chunks, ≥0.7 confidence)"""
    return {
        "chunks": [
            {"content": "ADA guidelines recommend...", "source": "ada_standards", "confidence": 0.85},
            {"content": "Clinical evidence shows...", "source": "clinical_guide", "confidence": 0.82},
            {"content": "Research indicates...", "source": "research_paper", "confidence": 0.78},
            {"content": "Best practices include...", "source": "ada_standards", "confidence": 0.80},
        ],
        "avg_confidence": 0.81,
        "source_count": 3
    }

@pytest.fixture
def mock_rag_sparse():
    """Mock RAG results with sparse coverage (triggers hybrid mode)"""
    return {
        "chunks": [
            {"content": "Limited information...", "source": "general_guide", "confidence": 0.55},
        ],
        "avg_confidence": 0.55,
        "source_count": 1
    }

@pytest.fixture
def mock_rag_empty():
    """Mock RAG results with no matches"""
    return {
        "chunks": [],
        "avg_confidence": 0.0,
        "source_count": 0
    }

@pytest.fixture
def mock_rag_device_docs():
    """Mock RAG results from device documentation"""
    return {
        "chunks": [
            {"content": "Dexcom G6 calibration steps...", "source": "dexcom_manual", "confidence": 0.92},
            {"content": "To calibrate your CGM...", "source": "dexcom_manual", "confidence": 0.88},
            {"content": "Sensor warmup period...", "source": "dexcom_faq", "confidence": 0.85},
        ],
        "avg_confidence": 0.88,
        "source_count": 2
    }

# ============================================
# LLM Mock Fixtures
# ============================================

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for controlled response generation"""
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value="Mock LLM response")
    return provider

@pytest.fixture
def mock_llm_hybrid_response():
    """Mock LLM response with proper hybrid attribution"""
    return """Based on ADA guidelines, meal timing affects glucose control [Source: ADA Standards of Care].

[General medical knowledge] Generally, eating at consistent times helps maintain stable blood sugar levels.

Your healthcare provider can offer personalized recommendations."""

@pytest.fixture
def mock_llm_parametric_only_response():
    """Mock LLM response that's heavily parametric"""
    return """[General medical knowledge] Diabetes management involves monitoring blood glucose levels.

[General medical knowledge] Exercise can help improve insulin sensitivity.

[General medical knowledge] A balanced diet is important for blood sugar control."""

@pytest.fixture
def mock_llm_unsafe_dosing_response():
    """Mock LLM response with unsafe parametric dosing (should be blocked)"""
    return """[General medical knowledge] You should take 10 units of insulin before meals.

Based on general understanding, increase your dose by 2 units if glucose is high."""

# ============================================
# Glooko Data Fixtures
# ============================================

@pytest.fixture
def mock_glooko_data():
    """Mock Glooko personal data"""
    return {
        "available": True,
        "glucose_readings": [
            {"timestamp": "2026-02-01T08:00:00", "value": 120, "unit": "mg/dL"},
            {"timestamp": "2026-02-01T12:00:00", "value": 145, "unit": "mg/dL"},
            {"timestamp": "2026-02-01T18:00:00", "value": 110, "unit": "mg/dL"},
        ],
        "average_glucose": 125,
        "time_in_range": 0.78
    }

@pytest.fixture
def mock_glooko_unavailable():
    """Mock Glooko when data not connected"""
    return {
        "available": False,
        "glucose_readings": [],
        "average_glucose": None,
        "time_in_range": None
    }

# ============================================
# Unified Agent Fixtures
# ============================================

@pytest.fixture
def unified_agent_with_mocks(mock_llm_provider, mock_rag_sufficient):
    """UnifiedAgent with mocked dependencies"""
    with patch('agents.unified_agent.get_llm_provider', return_value=mock_llm_provider):
        with patch('agents.unified_agent.ResearcherAgent') as mock_researcher:
            mock_researcher.return_value.search = AsyncMock(return_value=mock_rag_sufficient)
            from agents.unified_agent import UnifiedAgent
            agent = UnifiedAgent()
            yield agent

@pytest.fixture
def unified_agent_sparse_rag(mock_llm_provider, mock_rag_sparse):
    """UnifiedAgent configured to trigger hybrid mode"""
    with patch('agents.unified_agent.get_llm_provider', return_value=mock_llm_provider):
        with patch('agents.unified_agent.ResearcherAgent') as mock_researcher:
            mock_researcher.return_value.search = AsyncMock(return_value=mock_rag_sparse)
            from agents.unified_agent import UnifiedAgent
            agent = UnifiedAgent()
            yield agent

# ============================================
# Safety Auditor Fixtures
# ============================================

@pytest.fixture
def safety_auditor():
    """Fresh SafetyAuditor instance"""
    from agents.safety import SafetyAuditor
    return SafetyAuditor()

@pytest.fixture
def hybrid_response_safe():
    """Sample hybrid response that passes safety checks"""
    return {
        "answer": "According to ADA guidelines, consistent meal timing helps glucose control. [General medical knowledge] Regular monitoring is also beneficial.",
        "knowledge_breakdown": {
            "rag_ratio": 0.6,
            "parametric_ratio": 0.4,
            "primary_source_type": "hybrid"
        },
        "query": "How can I improve my glucose control?"
    }

@pytest.fixture
def hybrid_response_unsafe():
    """Sample hybrid response that fails safety checks (parametric dosing)"""
    return {
        "answer": "[General medical knowledge] Take 15 units of rapid-acting insulin before each meal.",
        "knowledge_breakdown": {
            "rag_ratio": 0.0,
            "parametric_ratio": 1.0,
            "primary_source_type": "parametric"
        },
        "query": "How much insulin should I take?"
    }

# ============================================
# Web API Test Fixtures
# ============================================

@pytest.fixture
def test_client():
    """FastAPI test client"""
    from fastapi.testclient import TestClient
    from web.app import app
    return TestClient(app)

@pytest.fixture
def async_test_client():
    """Async FastAPI test client for async tests"""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
```

---

## 5. Success Criteria

### 5.1 Quantitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Unit test pass rate | ≥ 95% | `pytest tests/test_hybrid_knowledge.py -v` |
| Integration test pass rate | ≥ 90% | `pytest tests/test_e2e_hybrid.py -v` |
| Safety test pass rate | 100% | `pytest tests/test_safety_hybrid.py -v` (critical) |
| Code coverage | ≥ 80% | `pytest --cov=agents --cov-report=term-missing` |
| Response time (95th percentile) | < 5s | Performance test with timing assertions |
| Safety audit pass rate | 100% for known-unsafe patterns | Safety pattern detection tests |

### 5.2 Qualitative Criteria

| Criterion | Verification Method |
|-----------|---------------------|
| Hybrid mode activates only when RAG insufficient | Integration tests with mocked RAG |
| Parametric dosing always blocked | Safety tests with dosing patterns |
| Device queries never use parametric when RAG unavailable | Device query safety tests |
| Attribution markers present in hybrid responses | Content inspection tests |
| Knowledge breakdown accurately reflects source mix | Calculation verification tests |
| Disclaimers appropriate for source type | Disclaimer content tests |

---

## 6. Coverage Matrix

### 6.1 Component Coverage

| Component | Unit Tests | Integration Tests | Safety Tests | Total Cases |
|-----------|------------|-------------------|--------------|-------------|
| `RAGQualityAssessment` | 8 | 2 | - | 10 |
| `KnowledgeBreakdown` | 6 | 3 | - | 9 |
| `_build_hybrid_prompt()` | 5 | 2 | - | 7 |
| `UnifiedResponse` | 5 | 4 | - | 9 |
| `audit_hybrid_response()` | - | 2 | 4 | 6 |
| Dosing safety checks | - | - | 5 | 5 |
| Device query safety | - | - | 5 | 5 |
| Citation enforcement | - | - | 4 | 4 |
| Parametric ratio calc | - | - | 3 | 3 |
| Web API endpoints | - | 5 | - | 5 |
| **TOTAL** | **24** | **18** | **21** | **63** |

### 6.2 Scenario Coverage

| Scenario | Test Files | Status |
|----------|------------|--------|
| RAG sufficient → pure RAG response | unit, e2e | Covered |
| RAG sparse → hybrid response | unit, e2e | Covered |
| RAG empty → parametric-heavy response | unit, e2e | Covered |
| Glooko data present → personal data prioritized | e2e | Covered |
| Parametric dosing advice → blocked | safety | Covered |
| Device query with RAG → allowed | safety, e2e | Covered |
| Device query without RAG → blocked | safety, e2e | Covered |
| Emergency query → safety first | e2e | Covered |
| Attribution markers present | unit, safety | Covered |
| Disclaimer matches source type | unit | Covered |
| Feedback endpoint functional | e2e | Covered |
| Response time acceptable | e2e | Covered |

---

## 7. Manual Testing Requirements

### 7.1 Exploratory Testing Scenarios

| Scenario | Test Steps | Expected Behavior |
|----------|------------|-------------------|
| **Real RAG interaction** | Query topics with known RAG content | Pure RAG responses, evidence-based badge |
| **Hybrid mode trigger** | Query obscure diabetes topics | Mixed sources badge, attribution markers |
| **Device safety** | Ask about device not in knowledge base | Appropriate refusal, suggests checking manual |
| **Badge display** | Submit various query types | Correct badge colors and labels |
| **Source categorization** | Check sources section | Sources grouped by type (clinical, device, etc.) |
| **Feedback buttons** | Click helpful/not helpful | Visual feedback, logged to CSV |
| **Disclaimer accuracy** | Check disclaimers for different response types | Parametric warning when ratio > 0.5 |

### 7.2 Edge Case Testing

| Edge Case | Test Method | Risk Level |
|-----------|-------------|------------|
| Very long queries | Manual input | Low |
| Multiple questions in one query | Manual input | Medium |
| Non-English input | Manual input | Low |
| Rapid sequential queries | Manual stress test | Medium |
| Network timeout during LLM call | Kill connection during request | High |
| Malformed Glooko data | Mock corrupted data | Medium |

### 7.3 Accessibility Testing

| Test | Method | Criteria |
|------|--------|----------|
| Badge contrast | Browser dev tools | WCAG AA (4.5:1 ratio) |
| Keyboard navigation | Tab through UI | All interactive elements reachable |
| Screen reader | NVDA/VoiceOver | Badges and sources announced clearly |
| Reduced motion | `prefers-reduced-motion` media query | No animations |
| High contrast mode | `prefers-contrast: more` | Enhanced borders visible |

---

## 8. Test Execution Plan

### 8.1 Execution Order

1. **Unit tests first** - Fast feedback, catch logic errors
   ```bash
   pytest tests/test_hybrid_knowledge.py -v --tb=short
   ```

2. **Safety tests second** - Critical path validation
   ```bash
   pytest tests/test_safety_hybrid.py -v --tb=short
   ```

3. **Integration tests third** - End-to-end validation
   ```bash
   pytest tests/test_e2e_hybrid.py -v --tb=short
   ```

4. **Full suite with coverage**
   ```bash
   pytest tests/test_hybrid_knowledge.py tests/test_safety_hybrid.py tests/test_e2e_hybrid.py \
     --cov=agents --cov=web --cov-report=html --cov-report=term-missing
   ```

### 8.2 CI/CD Integration

```yaml
# .github/workflows/test-hybrid.yml
name: Hybrid Knowledge Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run unit tests
        run: pytest tests/test_hybrid_knowledge.py -v
      - name: Run safety tests
        run: pytest tests/test_safety_hybrid.py -v
      - name: Run integration tests
        run: pytest tests/test_e2e_hybrid.py -v
      - name: Coverage report
        run: pytest --cov=agents --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Parametric dosing advice slips through | Low | Critical | 100% safety test coverage, multiple pattern checks |
| RAG quality assessment too aggressive | Medium | Medium | Tunable thresholds, monitoring in production |
| Attribution markers stripped by LLM | Low | High | Explicit prompt instructions, output validation |
| Device query misclassified | Medium | High | Comprehensive device pattern list, fallback to conservative |
| Performance degradation | Medium | Medium | Response time assertions, caching strategies |

---

## 10. Files to Create

| File | Purpose | Test Count |
|------|---------|------------|
| `tests/test_hybrid_knowledge.py` | Unit tests for hybrid knowledge components | 24 |
| `tests/test_e2e_hybrid.py` | End-to-end integration tests | 18 |
| `tests/test_safety_hybrid.py` | Safety-critical tests for hybrid responses | 21 |
| `tests/conftest.py` (additions) | Shared fixtures for mocking RAG/LLM | N/A |

**Total Test Cases: 63**
