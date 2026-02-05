# Diabetes Buddy - Current Architecture Analysis
**Generated:** February 4, 2026  
**Purpose:** Assess existing response quality and evaluation capabilities to inform enhancement planning

---

## Executive Summary

Diabetes Buddy has **strong foundational capabilities** for RAG quality assessment and safety validation, but **lacks automated response quality evaluation** and **structured feedback learning mechanisms**. The system excels at retrieval metrics and safety filtering but has minimal post-generation quality assessment and no automated hallucination detection beyond safety patterns.

**Key Findings:**
- ✅ **Robust RAG Quality Metrics**: Comprehensive confidence scoring, source diversity tracking
- ✅ **Strong Safety Validation**: Multi-tier safety auditor with dose detection and parametric violation checks
- ✅ **Experimentation Infrastructure**: A/B testing with statistical analysis (disabled by default)
- ⚠️ **Limited Feedback Loop**: Manual CSV logging exists, but no automated learning or adaptation
- ❌ **No Response Quality Scoring**: No automated evaluation of accuracy, relevance, or helpfulness
- ❌ **No Hallucination Detection**: Beyond safety patterns, no verification of factual claims
- ❌ **No Adaptive Prompts**: Static prompts; no learning from user feedback

---

## 1. RAG Quality Assessment (`agents/researcher_chromadb.py`)

### 1.1 Current Retrieval Metrics

**SearchResult Structure:**
```python
@dataclass
class SearchResult:
    """Represents a search result with quote, page number, and confidence."""
    quote: str
    page_number: Optional[int]
    confidence: float  # 0.0-1.0 based on cosine similarity
    source: str        # Human-readable source name
    context: str       # Contextual info (e.g., "Retrieved from user device source: CamAPS FX")
```

**Confidence Calculation:**
- **Method**: Cosine distance (0-2) converted to confidence (0-1)
  ```python
  confidence = 1.0 - (distance / 2.0)
  ```
- **User Device Boost**: +0.35 confidence boost for user-uploaded device manuals
  ```python
  USER_DEVICE_CONFIDENCE_BOOST = 0.35
  if is_user_device:
      confidence = min(1.0, confidence + USER_DEVICE_CONFIDENCE_BOOST)
  ```

**Quality Filtering:**
- Minimum chunk confidence threshold: `0.35` (configurable via `hybrid_knowledge.yaml`)
- Distance-based ranking using ChromaDB's vector search
- Source diversity tracking (unique source count)

### 1.2 Retrieval Method Signatures

```python
class ChromaDBBackend:
    def _search_collection(
        self, 
        source_key: str, 
        query: str, 
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        Search a ChromaDB collection for relevant chunks.
        
        Returns:
            List of SearchResult objects with confidence scores
        """
    
    def synthesize_answer(
        self,
        query: str,
        chunks: List[SearchResult],
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        """
        Provider-agnostic synthesis of answers using retrieved chunks.
        
        Returns:
            Dict with keys: {answer, llm_provider, llm_model, tokens_used, estimated_cost, cache_enabled}
        """
```

**Status:** ✅ **Fully Implemented**

---

## 2. Response Synthesis (`agents/unified_agent.py`)

### 2.1 Response Generation Pipeline

**Step-by-step pipeline:**
1. **Emergency Detection** → Check for critical symptoms
2. **Cohort Assignment** → A/B test assignment (if experimentation enabled)
3. **Glooko Data Loading** → Load user's glucose data (if available)
4. **Device Detection** → Identify user's devices from uploaded sources
5. **RAG Retrieval** → Search knowledge base (ChromaDB)
6. **RAG Quality Assessment** → Evaluate retrieval quality
7. **Hybrid Decision** → Decide if parametric augmentation needed
8. **Prompt Construction** → Build context-aware prompt
9. **LLM Synthesis** → Generate response with Groq/Gemini
10. **Safety Validation** → Safety auditor checks response

### 2.2 RAG Quality Assessment

```python
@dataclass
class RAGQualityAssessment:
    """Assessment of RAG retrieval quality for hybrid decision-making."""
    chunk_count: int
    avg_confidence: float
    max_confidence: float
    min_confidence: float
    sources_covered: list[str]  # Unique source names
    source_diversity: int       # Count of unique sources
    topic_coverage: str         # 'sufficient', 'partial', 'sparse'

    @property
    def is_sufficient(self) -> bool:
        """RAG is sufficient if ≥3 chunks with avg confidence ≥0.7."""
        return (
            self.chunk_count >= 3
            and self.avg_confidence >= 0.7
            and self.topic_coverage == "sufficient"
        )
```

**Assessment Method:**
```python
def _assess_rag_quality(self, results: list, query: str) -> RAGQualityAssessment:
    """
    Assess quality of RAG retrieval to determine if hybrid augmentation needed.
    
    Criteria for 'sufficient' coverage:
    - ≥3 chunks retrieved
    - Average confidence ≥0.7
    - At least 2 unique sources (for corroboration)
    
    Criteria for 'partial' coverage:
    - 1-2 chunks OR avg confidence 0.5-0.7
    - Some relevant information but gaps likely
    
    Criteria for 'sparse' coverage:
    - 0 chunks OR avg confidence <0.5
    - Needs parametric augmentation
    """
```

**Decision Logic:**
- **Sufficient RAG** (`chunk_count >= 3`, `avg_confidence >= 0.7`, `sources >= 2`):
  - Use pure RAG response
  - No parametric augmentation
  - High confidence in factual accuracy
  
- **Partial/Sparse RAG** (below thresholds):
  - Enable hybrid mode
  - Augment with LLM parametric knowledge
  - Flag `requires_enhanced_safety_check = True`

### 2.3 Post-Generation Validation

**Current Validation:**
- ✅ **Safety Auditor**: Scans for dangerous patterns (doses, medical advice)
- ✅ **Tier Classification**: Assigns safety tier (T1-T4) based on query intent
- ✅ **Disclaimer Injection**: Adds mandatory disclaimers
- ❌ **No Factual Verification**: Does not verify claims against sources
- ❌ **No Hallucination Detection**: Beyond safety patterns
- ❌ **No Relevance Scoring**: Does not assess answer quality

**Status:** ⚠️ **Partial** - Safety validation exists, quality evaluation missing

---

## 3. Safety Auditor (`agents/safety.py`)

### 3.1 Validation Methods

```python
class SafetyAuditor:
    def audit_text(self, text: str, query: str) -> AuditResult:
        """Basic audit without triage - scans for dangerous patterns."""
    
    def audit_response(
        self, 
        query: str, 
        response: str, 
        conversation_history: Optional[List] = None
    ) -> SafeResponse:
        """Full audit with triage, safety tier classification, and content filtering."""
    
    def audit_hybrid_response(
        self,
        query: str,
        response: str,
        rag_quality: dict,
        knowledge_breakdown: dict,
        conversation_history: Optional[List] = None,
    ) -> HybridAuditResult:
        """Extended audit for hybrid RAG + parametric responses."""
```

### 3.2 Safety Tier Definitions

| Tier | Criteria | Action | Example Queries |
|------|----------|--------|-----------------|
| **T4 (CRITICAL)** | Dosing calculations, specific medical advice | BLOCK + Redirect | "How much insulin should I take?" |
| **T3 (HIGH)** | Treatment changes, device configuration | FILTER + Enhanced Disclaimer | "Should I change my basal rate?" |
| **T2 (MEDIUM)** | Educational content with medical implications | Disclaimer Only | "What is time in range?" |
| **T1 (LOW)** | General information, factual queries | Pass Through | "What is a CGM?" |

### 3.3 Medical Claim Verification

**Parametric Violation Detection:**
```python
PARAMETRIC_DOSING_PATTERNS = [
    (r'\b(need|require|should\s+take|recommend)\s+.{0,30}\d+\.?\d*\s*(u|units?)\b', 'recommended_dose'),
    (r'\b(typical|average|standard)\s+(dose|bolus|basal)\s+.{0,20}\d+', 'typical_dose'),
    (r'\bstart\s+with\s+\d+\.?\d*\s*(u|units?)\b', 'starting_dose'),
    (r'\b\d+\.?\d*\s*(u|units?)/(kg|kilogram)\b', 'dose_per_kg_ratio'),
]

RAG_CITATION_PATTERNS = [
    r'\b(OpenAPS|Loop|AndroidAPS)\s+(documentation|docs|manual)\b',
    r'\b(ADA|American Diabetes Association)\s+(Standards|guidelines)\b',
    r'\baccording to\s+(the\s+)?(documentation|manual|guidelines)\b',
]
```

**Hybrid-Specific Safety Checks:**
- ✅ Detects device queries without RAG citations
- ✅ Flags parametric dosing advice
- ✅ Monitors parametric ratio (`> 30%` triggers enhanced check)
- ❌ Does NOT verify parametric claims against RAG sources
- ❌ Does NOT score hallucination likelihood

**Status:** ✅ **Exists** - Strong pattern-based safety, but no source verification

---

## 4. Feedback & Learning Systems

### 4.1 Session Management (`agents/session_manager.py`)

**Session Data Structure:**
```json
{
  "session_id": "uuid-v4",
  "created_at": "2026-02-04T12:00:00",
  "updated_at": "2026-02-04T12:15:00",
  "exchanges": [
    {
      "query": "How does auto mode work?",
      "response": "Auto mode...",
      "timestamp": "2026-02-04T12:00:05",
      "classification": {
        "category": "device_query",
        "confidence": 0.92
      }
    }
  ]
}
```

**Storage Location:** `data/sessions/{session_id}.json`

### 4.2 Feedback Collection

**Web API Endpoint:** `/api/feedback`

**Feedback Data Structure:**
```python
class FeedbackRequest(BaseModel):
    timestamp: str
    message_id: str
    feedback: str  # 'helpful' or 'not-helpful'
    primary_source_type: Optional[str] = None
    knowledge_breakdown: Optional[dict] = None
```

**CSV Logging:** `data/feedback.csv`

**Tracked Metrics:**
- Feedback type (helpful/not-helpful)
- Primary source type (rag/parametric/glooko)
- RAG ratio (0.0-1.0)
- Parametric ratio (0.0-1.0)
- Blended confidence
- Session ID hash (anonymized)

**Feedback Stats Endpoint:** `/api/feedback-stats`
- Returns: helpful rate, source type correlations, RAG vs parametric effectiveness

### 4.3 Learning Mechanisms

**Device Personalization (`agents/device_personalization.py`):**
```python
class DevicePersonalization:
    def adjust_boost_from_feedback(
        self, 
        device_name: str, 
        feedback_sentiment: str
    ) -> float:
        """
        Adjust device priority boost based on user feedback.
        
        Learning rate decays over time to stabilize after ~30 samples.
        """
```

**Current Status:**
- ⚠️ Device-specific boost adjustment exists
- ❌ No query expansion from negative feedback
- ❌ No reranking based on historical performance
- ❌ No negative example filtering
- ❌ No adaptive prompt refinement

**Feedback Loop Agent:** ❌ **Does NOT exist as a dedicated component**

**Status:** ⚠️ **Partial** - Data collected but minimal learning/adaptation

---

## 5. Experimentation & Analytics

### 5.1 A/B Testing (`agents/experimentation.py`)

**Current Experiment:** `hybrid_vs_pure_rag`

**Cohorts:**
- **Control (50%)**: Pure RAG responses (parametric disabled)
- **Treatment (50%)**: Hybrid RAG + parametric augmentation

**Configuration:**
```yaml
experimentation:
  enabled: false  # Currently disabled
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

**Assignment Method:**
```python
def get_cohort_assignment(self, session_id: str, experiment_name: str) -> str:
    """Deterministic assignment based on session_id hash."""
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()
    bucket = int(session_hash[:8], 16) % 100
    return cohort_config.get_cohort_for_bucket(bucket)
```

### 5.2 Quality Metrics (`agents/analytics.py`)

**ExperimentAnalytics Class:**
```python
def get_experiment_status(
    self, 
    experiment_name: str = "hybrid_vs_pure_rag", 
    min_sample_size: int = 620
) -> ExperimentStatistics:
    """
    Fetch live experiment statistics with t-test and effect size.
    
    Returns:
        - Control vs treatment sample sizes
        - Helpful rates for each cohort
        - P-value (two-tailed t-test)
        - Cohen's d (effect size)
        - Winner recommendation
    """
```

| Metric | Tracked | Location | Notes |
|--------|---------|----------|-------|
| **Response latency** | ⚠️ | `unified_agent.py:response_time` | Tracked in UnifiedResponse but not aggregated |
| **Hallucination rate** | ❌ | N/A | Not measured |
| **User satisfaction** | ✅ | `data/feedback.csv` | Manual thumbs up/down |
| **Accuracy scores** | ❌ | N/A | Not measured |
| **Parametric ratio** | ✅ | `knowledge_breakdown.parametric_ratio` | Per-response |
| **RAG confidence** | ✅ | `knowledge_breakdown.rag_confidence` | Per-response |
| **Source diversity** | ✅ | `RAGQualityAssessment.source_diversity` | Per-query |

**Status:** ⚠️ **Partial** - Infrastructure exists but minimal automated analysis

---

## 6. Testing Coverage

### 6.1 Existing Test Files

```
tests/
├── test_comprehensive.py           [Integration tests for full pipeline]
├── test_response_quality.py        [LLM-based quality evaluation framework]
├── test_response_quality_comprehensive.py [7-dimension quality scoring]
├── test_retrieval_quality.py       [RAG retrieval accuracy tests]
├── test_safety_patterns.py         [Safety auditor pattern detection]
├── test_safety_tiers.py            [Tier classification tests]
├── test_safety_hybrid.py           [Hybrid response safety validation]
├── test_experimentation.py         [A/B testing infrastructure]
├── test_experimentation_integration.py [End-to-end experiment flow]
├── test_device_detection.py        [Device detection from PDFs]
├── test_device_personalization.py  [Device priority boost logic]
├── test_glooko_query.py            [Glooko data analysis]
└── ... (303 total test cases)
```

### 6.2 Response Quality Test Cases

**Test Suite: `test_response_quality_comprehensive.py`**

**7-Dimension Quality Framework:**
```python
@dataclass
class QualityScore:
    answer_relevancy: DimensionScore       # 1-5 scale
    practical_helpfulness: DimensionScore  # 1-5 scale
    knowledge_guidance: DimensionScore     # 1-5 scale
    tone_professionalism: DimensionScore   # 1-5 scale
    clarity_structure: DimensionScore      # 1-5 scale
    source_integration: DimensionScore     # 1-5 scale
    safety_appropriateness: SafetyScore    # Pass/Fail
```

**Example Test Cases:**
- Category A: Well-supported device queries (expected 4-5 scores)
- Category B: Sparse knowledge queries (should guide user appropriately)
- Category C: Safety-critical queries (must pass safety checks)
- Category D: Tone & empathy evaluation

**Note:** This test framework is **manually triggered** and not integrated into automated evaluation.

### 6.3 Coverage Gaps

**What's NOT Currently Tested:**
- ❌ Automated response quality scoring in production
- ❌ Hallucination detection against ground truth
- ❌ Factual accuracy verification (claims vs sources)
- ❌ Temporal staleness of knowledge
- ❌ User feedback integration loops
- ❌ Adaptive prompt performance over time
- ❌ Citation accuracy (do cited sources support claims?)

**Status:** ⚠️ **Strong test infrastructure, but no automated production evaluation**

---

## 7. Complete Query Flow Trace

**Example Query:** "How does my pump's auto mode work?"

### Flow Diagram:
```
User Query (web/app.py)
    ↓
[Rate Limiting] (web/app.py:RateLimiter.is_allowed)
    ↓
[Entry Point] POST /api/query (web/app.py:query_endpoint)
    ↓
[Unified Agent] UnifiedAgent.process_stream() (agents/unified_agent.py:377)
    ↓
[Emergency Check] _detect_emergency_query() (agents/unified_agent.py:1162)
    ↓
[Cohort Assignment] _get_cohort_assignment() (agents/unified_agent.py:1113)
    ↓
[Glooko Loading] _load_glooko_context() (agents/unified_agent.py:1203)
    ↓
[Device Detection] UserSourceManager.get_user_devices() (agents/source_manager.py)
    ↓
[RAG Retrieval] ResearcherAgent.research() (agents/researcher_chromadb.py)
    ↓
[RAG Quality] _assess_rag_quality() (agents/unified_agent.py:1229)
    ↓
[Hybrid Decision] is_sufficient check (agents/unified_agent.py:973)
    ├─[Sufficient]─→ Pure RAG response
    └─[Sparse]────→ Hybrid prompt + parametric knowledge
    ↓
[LLM Synthesis] _generate_with_fallback() (agents/unified_agent.py:661)
    ↓
[Safety Audit] SafetyAuditor.audit_hybrid_response() (agents/safety.py:560)
    ↓
[Session Storage] SessionManager.add_exchange() (agents/session_manager.py:71)
    ↓
[Streaming Response] SSE chunks to web client (web/app.py)
```

### Detailed Steps:

1. **Entry:** `web/app.py:563` - `async def query_endpoint(request, query)`
   - Rate limit check
   - Conversation ID validation

2. **Unified Processing:** `agents/unified_agent.py:377` - `def process_stream(query, session_id, conversation_history)`
   - Emergency detection
   - Cohort assignment for A/B testing

3. **Retrieval:** `agents/researcher_chromadb.py` - `ResearcherAgent.research(query, top_k=10)`
   - ChromaDB vector search
   - Confidence scoring
   - Device boost application

4. **Quality Assessment:** `agents/unified_agent.py:1229` - `_assess_rag_quality(results, query)`
   - Calculate chunk count, avg confidence
   - Determine topic coverage

5. **Synthesis:** `agents/unified_agent.py:661` - `_generate_with_fallback(prompt, provider, config)`
   - Groq-first routing
   - Gemini fallback on failure
   - Token tracking

6. **Safety Validation:** `agents/safety.py:560` - `audit_hybrid_response(...)`
   - Dose pattern detection
   - Parametric violation checks
   - Tier classification
   - Disclaimer injection

7. **Storage:** `agents/session_manager.py:71` - `add_exchange(session_id, query, response)`
   - Persist to `data/sessions/{session_id}.json`

---

## 8. Capability Summary Matrix

| Capability | Status | Location | Implementation Notes |
|------------|--------|----------|---------------------|
| **Retrieval Quality Metrics** | ✅ | `agents/researcher_chromadb.py:332-415` | Confidence scoring, source diversity, device boost |
| **RAG Quality Assessment** | ✅ | `agents/unified_agent.py:1229-1302` | Topic coverage classification (sufficient/partial/sparse) |
| **Response Validation** | ⚠️ | `agents/safety.py:246-560` | Safety patterns only, no quality scoring |
| **Hallucination Detection** | ❌ | N/A | No implementation beyond safety patterns |
| **Factual Verification** | ❌ | N/A | Does not verify claims against sources |
| **Feedback Collection** | ✅ | `web/app.py:1431-1472` | CSV logging with knowledge breakdown |
| **Feedback Analysis** | ✅ | `web/app.py:1472-1542` | Statistics endpoint (helpful rate, correlations) |
| **Adaptive Prompts** | ❌ | N/A | Static prompts, no learning from feedback |
| **Device Personalization** | ⚠️ | `agents/device_personalization.py:116` | Boost adjustment exists but limited |
| **Safety Claim Verification** | ⚠️ | `agents/safety.py:279-317` | Pattern detection, no source cross-check |
| **Learning Mechanisms** | ❌ | N/A | No query expansion, reranking, or negative examples |
| **Quality Analytics** | ⚠️ | `agents/analytics.py` | A/B testing framework (disabled) |
| **Experimentation** | ⚠️ | `agents/experimentation.py` | Full infrastructure but disabled by default |
| **Source Citation** | ✅ | `agents/unified_agent.py:1304-1327` | Tracks sources, confidence scores |
| **Emergency Detection** | ✅ | `agents/unified_agent.py:1162-1202` | Pattern-based with severity scoring |
| **Response Time Tracking** | ✅ | `agents/unified_agent.py:UnifiedResponse.response_time` | Tracked but not aggregated |
| **LLM Provider Routing** | ✅ | `agents/unified_agent.py:596-659` | Smart routing based on query type |
| **Cost Tracking** | ✅ | `agents/llm_provider.py` | Token usage and estimated cost |

---

## 9. Gap Analysis

### 9.1 Fully Implemented ✅

- **RAG retrieval quality metrics**: Confidence scoring, source diversity, device prioritization
- **Safety auditing**: Multi-tier safety with dose detection and parametric violation checks
- **Feedback data collection**: CSV logging with source type breakdown
- **Session management**: Conversation history persistence
- **Experimentation infrastructure**: A/B testing framework with statistical analysis
- **Emergency detection**: Pattern-based critical symptom detection
- **Source citation tracking**: Maintains provenance of all knowledge sources

### 9.2 Partially Implemented ⚠️

- **Response validation**: Safety checks exist, but no quality/accuracy scoring
- **Feedback analytics**: Statistics endpoint exists, but no automated action
- **Device personalization**: Boost adjustment from feedback, but limited scope
- **Quality monitoring**: Data captured but not systematically analyzed
- **Testing coverage**: Comprehensive test suite, but not integrated into production evaluation

### 9.3 Not Implemented ❌

**Critical Gaps:**
1. **Automated Response Quality Evaluation**
   - No LLM-as-judge scoring in production
   - No accuracy verification against sources
   - No relevance/helpfulness metrics
   - No hallucination detection

2. **Factual Claim Verification**
   - Does not cross-check parametric claims against RAG sources
   - No ground truth comparison
   - No citation accuracy validation

3. **Feedback Learning Loop**
   - No query expansion from negative feedback
   - No reranking based on user preferences
   - No negative example filtering
   - No adaptive prompt refinement

4. **Response Quality Analytics**
   - No aggregated quality metrics dashboard
   - No trend analysis of response accuracy
   - No hallucination rate tracking
   - No source type effectiveness analysis

5. **Knowledge Staleness Monitoring**
   - Config mentions thresholds, but no active monitoring
   - No alerts for outdated content
   - No automatic knowledge refresh triggers

---

## 10. Recommendations

### Priority 1: Critical Gaps (Required for Production Quality Assurance)

1. **Implement LLM-as-Judge Response Evaluation**
   - Leverage existing `test_response_quality_comprehensive.py` framework
   - Deploy 7-dimension scoring in production (async post-response)
   - Track: relevancy, helpfulness, safety, accuracy, tone
   - Store evaluations for trend analysis

2. **Build Hallucination Detection System**
   - Cross-check parametric claims against RAG sources
   - Flag unverifiable statements
   - Score confidence in factual assertions
   - Alert on high-confidence hallucinations

3. **Create Feedback Learning Loop**
   - Automated query expansion for negative feedback
   - Rerank sources based on user satisfaction
   - Filter negative examples from future retrievals
   - Adjust parametric usage thresholds dynamically

4. **Deploy Quality Analytics Dashboard**
   - Real-time monitoring of response quality scores
   - Hallucination rate tracking
   - Source type effectiveness (RAG vs parametric)
   - Temporal trends and anomaly detection

### Priority 2: Enhancements (Improve User Experience)

1. **Adaptive Prompt Engineering**
   - Learn optimal prompts from high-rated responses
   - A/B test prompt variations automatically
   - Personalize prompts based on user device context

2. **Source Verification Module**
   - Validate citations actually support claims
   - Score strength of source-claim alignment
   - Flag weak or missing citations

3. **Knowledge Staleness Automation**
   - Scheduled checks for outdated content (30/90 day thresholds)
   - Automatic ingestion of updated guidelines (ADA, Australian)
   - Version tracking for medical knowledge sources

4. **Enable A/B Testing by Default**
   - Turn on `experimentation.enabled: true`
   - Monitor hybrid vs pure RAG performance
   - Make data-driven decisions on parametric usage

### Priority 3: Future Considerations (Long-term Innovation)

1. **Multi-Modal Response Evaluation**
   - Evaluate clarity of visualizations (glucose charts)
   - Assess tone appropriateness for emergency queries
   - User engagement metrics (time-to-helpful-rating)

2. **Retrieval-Augmented Verification (RAV)**
   - Use RAG not just for generation, but for fact-checking
   - Generate claims, then retrieve evidence, then verify
   - Self-critique loop before final response

3. **User-Specific Quality Profiles**
   - Learn individual preferences for detail level
   - Adapt tone based on user history
   - Personalize safety disclaimer verbosity

4. **Continuous Learning Pipeline**
   - Automatically retrain device detection from uploads
   - Fine-tune embedding model on user queries
   - Update safety patterns from feedback flags

---

## Appendix: Code Snippets

### A. Key Method Signatures

**RAG Quality Assessment:**
```python
# agents/unified_agent.py:1229
def _assess_rag_quality(self, results: list, query: str) -> RAGQualityAssessment:
    """
    Assess quality of RAG retrieval to determine if hybrid augmentation needed.
    
    Returns:
        RAGQualityAssessment with:
        - chunk_count: Number of retrieved chunks
        - avg_confidence: Mean confidence score (0-1)
        - sources_covered: List of unique source names
        - topic_coverage: 'sufficient' | 'partial' | 'sparse'
    """
```

**Safety Auditing:**
```python
# agents/safety.py:560
def audit_hybrid_response(
    self,
    query: str,
    response: str,
    rag_quality: dict,
    knowledge_breakdown: dict,
    conversation_history: Optional[List] = None,
) -> HybridAuditResult:
    """
    Extended audit for hybrid RAG + parametric responses.
    
    Checks:
    - Dose patterns
    - Parametric violations (unattributed claims)
    - Device queries without RAG citations
    - Safety tier classification
    """
```

**Feedback Logging:**
```python
# web/app.py:1431
@app.post("/api/feedback")
async def log_feedback(request: Request, feedback: FeedbackRequest):
    """
    Log user feedback on response quality.
    
    Tracks:
    - helpful/not-helpful sentiment
    - Primary source type (rag/parametric/glooko)
    - Knowledge breakdown ratios
    - Session ID (anonymized)
    """
```

### B. Configuration Files

**Hybrid Knowledge Configuration (`config/hybrid_knowledge.yaml`):**
```yaml
rag_quality:
  min_chunks: 3
  min_confidence: 0.7
  min_sources: 2
  min_chunk_confidence: 0.35

parametric_usage:
  max_ratio: 0.7  # warn if >70% parametric
  confidence_score: 0.6

safety:
  enhanced_check_threshold: 0.3  # trigger if parametric >30%

experimentation:
  enabled: false  # Currently disabled
  experiments:
    - name: "hybrid_vs_pure_rag"
      cohorts:
        control: 50
        treatment: 50
      min_sample_size: 620
```

### C. Data Structures

**UnifiedResponse:**
```python
@dataclass
class UnifiedResponse:
    success: bool
    answer: str
    sources_used: list[str]
    glooko_data_available: bool
    disclaimer: str = ""
    priority: str = "NORMAL"
    cohort: Optional[str] = None
    rag_quality: Optional[RAGQualityMetrics] = None
    requires_enhanced_safety_check: bool = False
    knowledge_breakdown: Optional[KnowledgeBreakdown] = None
    llm_info: Optional[dict] = None
    response_time: Optional[dict] = None
```

**RAGQualityAssessment:**
```python
@dataclass
class RAGQualityAssessment:
    chunk_count: int
    avg_confidence: float
    max_confidence: float
    min_confidence: float
    sources_covered: list[str]
    source_diversity: int
    topic_coverage: str  # 'sufficient', 'partial', 'sparse'

    @property
    def is_sufficient(self) -> bool:
        return (
            self.chunk_count >= 3
            and self.avg_confidence >= 0.7
            and self.topic_coverage == "sufficient"
        )
```

---

## Analysis Complete

**Key Takeaway:** Diabetes Buddy has **excellent retrieval infrastructure** and **strong safety mechanisms**, but lacks **automated response quality evaluation** and **closed-loop feedback learning**. The foundation is solid; the next phase should focus on **post-generation quality assurance** and **continuous improvement from user feedback**.

**Recommended Next Steps:**
1. Deploy LLM-as-judge evaluation (use existing test framework)
2. Build hallucination detection module
3. Create feedback learning loop with query expansion
4. Enable A/B testing to validate improvements

**Last Updated:** February 4, 2026  
**Analyst:** GitHub Copilot CLI
