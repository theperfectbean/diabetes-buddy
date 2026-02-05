# Quick Reference: Meal Management Implementation

## What Was Added?

### 1. Meal Query Detection (Triage)
```python
# File: agents/triage.py
# Method: _detect_meal_management_query(query: str) -> Optional[Classification]

# Detects queries about slow-carb/high-fat foods that cause delayed spikes
# Returns HYBRID classification with USER_SOURCES priority if detected

agent = TriageAgent()
result = agent._detect_meal_management_query("Pizza causes spikes 6 hours later")
# Returns: Classification(category=HYBRID, confidence=0.95, ...)
```

### 2. Specialized Prompts (Unified Agent)
```python
# File: agents/unified_agent.py
# Method: _build_meal_management_prompt(...) -> str

# Builds context-aware prompts with:
# - Mechanism explanation (why delayed spikes happen)
# - Device-specific strategies (extracted from manuals)
# - Practical monitoring guidance
# - Healthcare team consultation

prompt = agent._build_meal_management_prompt(
    query="Pizza?",
    kb_context="Extended bolus available",
    food_mention="pizza",
    user_devices=["YpsoPump"]
)
```

### 3. Fallback Logic
```python
# File: agents/unified_agent.py
# Method: _should_provide_detailed_response(...) -> tuple[bool, str]

# Checks if we have enough information
# Returns: (should_provide, response_type)
# - "provide_detailed_explanation": Rich device features
# - "provide_general_guidance": Some guidance available
# - "request_more_context": Ask for clarification

should_provide, type = agent._should_provide_detailed_response(
    query="Pizza?",
    retrieved_chunks=[...device info...]
)
```

## Keywords & Detection Rules

### Food Types (20 keywords)
```
pizza, pasta, chinese food, fried, fatty, creamy, cheese, slow carb, 
high fat, protein, ice cream, chow mein, pad thai, donuts, pastry, 
baked goods, fries, burger, pho, ramen
```

### Delayed Patterns (21 keywords)
```
delayed spike, delayed high, hours later, overnight spike, slow rise,
still rising, keeps going up, spike after, hours after eating,
6/5/4/3/2 hours later, blood sugar keeps rising, won't come down,
prolonged high, continues to rise, manage, handle, absorb
```

### Management Terms (13 keywords)
```
extended bolus, combination bolus, split dose, dual wave,
slowly absorbed meal, fat and protein, meal boost, ease-off,
carb entry, extended delivery, split percentage, gradual delivery,
meal feature
```

## Detection Rules

A query is classified as meal management if:
- Food type + delayed pattern keywords, OR
- Food type + management terms, OR
- Food type + high mention (in context of meals), OR
- 3+ meal-related keywords total

## Testing

```bash
# Run all meal management tests
pytest tests/test_meal_management.py -v

# Run specific test class
pytest tests/test_meal_management.py::TestMealManagementDetection -v

# Run single test
pytest tests/test_meal_management.py::TestMealManagementDetection::test_pizza_with_delayed_spike -v
```

## Test Coverage

- **Detection Tests** (8): Pizza, pasta, Chinese food, fatty foods, CamAPS features
- **Prompt Tests** (3): Mechanism, device guidance, no deflections
- **Keyword Tests** (4): Pizza, patterns, bolus, categories
- **Quality Tests** (5): Mechanism, technique, provider mention, no doses
- **Integration Tests** (2): End-to-end flows

## How It Works

```
User Query: "Pizza causes spikes 6 hours after eating"
    ↓
Triage.classify() called
    ↓
_detect_meal_management_query() checks keywords
    ↓
Finds: "pizza" + "6 hours" + "spikes"
    ↓
Returns: HYBRID classification (90-95% confidence)
    ↓
Secondary categories: USER_SOURCES, KNOWLEDGE_BASE, CLINICAL_GUIDELINES
    ↓
UnifiedAgent.process() receives HYBRID query
    ↓
_is_meal_management_query() = True
    ↓
_build_meal_management_prompt() used instead of generic prompt
    ↓
Response includes:
  1. WHY: Fat delays absorption, timing 3-6 hours
  2. HOW: Device extended bolus feature (if available)
  3. WHEN: Monitor at 2 hours and 5 hours
  4. WHO: "Consult your healthcare team"
```

## Common Modifications

### Adding a New Food
```python
# In agents/triage.py, COMPLEX_MEAL_KEYWORDS["food_types"]
"pizza", "pasta", ... "your_food_here"
```

### Adding a New Delayed Pattern
```python
# In agents/triage.py, COMPLEX_MEAL_KEYWORDS["delayed_patterns"]
"delayed spike", "hours later", ... "your_pattern_here"
```

### Adjusting Detection Confidence
```python
# In agents/triage.py, _detect_meal_management_query()
confidence = min(0.95, 0.7 + (total_matches * 0.1))  # Change formula
```

### Testing a New Query
```python
from agents.triage import TriageAgent

agent = TriageAgent()
result = agent._detect_meal_management_query("Your query here")
if result:
    print(f"Detected: {result.confidence:.1%} confidence")
else:
    print("Not detected as meal management")
```

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Meal detection | <1ms | Keyword matching only, no LLM |
| Classification | 2-5s | With LLM if fallthrough |
| Prompt building | <10ms | Template instantiation |
| Full response | 5-10s | Including LLM generation |

## Safety Guardrails

- ✅ No specific insulin dose recommendations
- ✅ Healthcare team consultation required
- ✅ Evidence-based ranges only
- ✅ No medical advice beyond education
- ✅ Device features extracted, not invented

## Troubleshooting

### Query Not Being Detected
1. Check if it contains food type keyword
2. Check if it has delayed pattern OR management term
3. Verify total keywords >= 3 if no food + pattern combo
4. Use `agent._detect_meal_management_query(query)` to debug

### Response Too Generic
1. Ensure device manual is in knowledge base
2. Check if `kb_context` contains device features
3. Verify retrieval is prioritizing USER_SOURCES
4. Review `_should_provide_detailed_response()` logic

### Confidence Too Low
1. Add more keyword variations to COMPLEX_MEAL_KEYWORDS
2. Lower confidence threshold in `_detect_meal_management_query()`
3. Adjust keyword match calculation formula
4. Check if query has enough meal-related keywords

## Integration Points

- **Triage**: Query classification happens first (early exit for meal queries)
- **Unified Agent**: Meal queries routed to specialized prompt builder
- **Researcher**: Knowledge base search prioritizes USER_SOURCES for meal queries
- **Response Quality**: Meal responses validated with specialized checks
- **Safety**: All responses include healthcare team guidance

---

**Last Updated**: 2026-02-04
**Status**: Production Ready
**Backward Compatible**: Yes
