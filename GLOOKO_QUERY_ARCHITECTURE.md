# Glooko Query Architecture

## Overview

This document outlines the architecture for enabling natural language queries over Glooko export data, allowing users to ask questions about their diabetes metrics and receive data-driven answers.

---

## Phase 1: Architecture Planning

### 1. Query Types to Support

#### Temporal Queries
Questions about specific time ranges or recurring patterns:
- "What was my average blood sugar last Tuesday?"
- "Show me my lows from January 15-20"
- "How many times did I go low in December?"
- "What's my glucose trend this week?"

**Implementation:** Date parsing with fuzzy matching (e.g., "last Tuesday", "January 15-20", "past 2 weeks"), filtering by timestamp, calculating metrics for range.

#### Pattern Queries
Questions about recurring phenomena or patterns:
- "When do I typically experience dawn phenomenon?"
- "What days had post-meal spikes?"
- "Which hours are my glucose most variable?"
- "Do I have a pattern around exercise?"

**Implementation:** Identify recurring temporal patterns (hour of day, day of week), group events by pattern, statistical analysis of grouped data.

#### Statistical Queries
Questions about aggregate metrics and performance:
- "What's my time in range for the past 2 weeks?"
- "How many hypoglycemic events last month?"
- "What's my average glucose?"
- "What percentage of readings were above 180?"

**Implementation:** Aggregate operations (mean, median, count, percentiles), metric calculations (TIR, TAR, TBR), temporal filtering.

#### Correlation Queries
Questions about relationships between variables:
- "How does my blood sugar respond after exercise?"
- "What's my insulin sensitivity trend?"
- "Do meals with higher carbs cause higher spikes?"
- "How does stress affect my glucose?"

**Implementation:** Requires multiple data fields, calculate post-event deltas, linear regression for trends, grouping and comparison.

---

### 2. Integration Points

#### Triage Agent (agents/triage.py)
- Recognize data queries and route to "glooko_data" source
- Distinguish between knowledge queries and personal data queries
- Examples of glooko_data triggers: "my blood sugar", "my glucose", "my time in range", "my readings", "last week", "how many times", "average glucose", "trend", "pattern"
- Return classification: `{"source": "glooko_data", "intent": "temporal|pattern|statistical|correlation"}`

#### New GlookoQueryAgent (agents/glooko_query.py)
- Handles natural language to data query translation
- Loads and parses analysis JSON files
- Executes queries against structured data
- Returns formatted answers with evidence

#### Web UI Updates (web/index.html, web/static/app.js)
- Add "Your Glooko Data" to sources sidebar
- Display data queries with special formatting (tables, inline stats)
- Show data query responses with context (date range, disclaimer)

#### Safety Auditor (agents/safety.py)
- Ensure data interpretations include appropriate disclaimers
- Verify responses don't overstate confidence in data
- Add warnings for edge cases (small sample size, incomplete data)

---

### 3. Data Query Architecture

#### Data Sources
- **Primary:** `data/analysis/*.json` - Structured analysis files with parsed diabetes metrics
- **Schema:** Expected fields: timestamp, glucose, meal, exercise, insulin, HbA1c, carbs, etc.
- **Format:** JSON arrays of events with standardized field names

#### Query Processing Pipeline

```
User Question
    ↓
Triage Agent (classification + intent)
    ↓
GlookoQueryAgent
    ├→ Parse intent with Gemini (date range, metrics, aggregation)
    ├→ Load analysis JSON files
    ├→ Filter by date/temporal criteria
    ├→ Execute pandas operations
    ├→ Calculate requested metrics
    └→ Format response with context
    ↓
Safety Auditor (verify disclaimers)
    ↓
Response to User
```

#### GlookoQueryAgent Features
- **Intent parsing:** Gemini interprets query to extract:
  - Date range (if specified)
  - Metric type (glucose, TIR, events, trend)
  - Aggregation type (average, max, count, percentile)
  - Pattern criteria (time of day, day of week)
- **Data loading:** Find most recent analysis files, load JSON
- **Query execution:** Pandas filtering and aggregation operations
- **Response formatting:** Units, context, evidence excerpts

---

### 4. Example Workflow

**User asks:** "What was my average glucose last week?"

```
1. User enters question in chat UI
   ↓
2. Triage Agent processes:
   Input: "What was my average glucose last week?"
   Output: {
     "source": "glooko_data",
     "intent": "statistical",
     "confidence": 0.95
   }
   ↓
3. Web API routes to GlookoQueryAgent
   ↓
4. GlookoQueryAgent executes:
   a) Parse query with Gemini:
      - Metric: "glucose" (blood sugar)
      - Aggregation: "average"
      - Date range: last 7 days (from today)
   
   b) Load data/analysis/analysis_YYYYMMDD_HHMMSS.json
   
   c) Filter: readings from Jan 21-27, 2026
   
   d) Calculate: mean(glucose) = 142 mg/dL
   
   e) Format response with context:
      - Convert units if needed
      - Add statistical context (median, range)
      - Include sample count
   ↓
5. Safety Auditor reviews:
   - Verifies appropriate disclaimers included
   - Checks data completeness
   - Adds warnings if needed (e.g., low sample size)
   ↓
6. Response sent to user:
   "Your average glucose last week was 142 mg/dL 
    (7.9 mmol/L). Based on 127 readings from 
    Jan 21-27, 2026. You spent 68% in range 
    (70-180 mg/dL).
    
    [Note: This analysis is based on your uploaded 
    Glooko data. Discuss trends with your healthcare team.]"
```

---

## Phase 2: Implementation Tasks

### 2.1 Update Triage Agent (agents/triage.py)
- [ ] Add "glooko_data" as classification category
- [ ] Add recognition patterns for personal data queries
- [ ] Update examples and training data
- [ ] Return intent subclassification (temporal, pattern, statistical, correlation)

### 2.2 Create GlookoQueryAgent (agents/glooko_query.py)
- [ ] Class: `GlookoQueryAgent`
- [ ] Method: `process_query(question: str, analysis_files: list[str]) -> dict`
- [ ] Sub-methods:
  - `parse_intent(question: str) -> dict` - Use Gemini to extract intent
  - `load_data(file_path: str) -> DataFrame` - Load analysis JSON
  - `execute_query(df: DataFrame, intent: dict) -> dict` - Pandas operations
  - `format_response(result: dict, intent: dict) -> str` - Add context and disclaimers
- [ ] Error handling for: no data, ambiguous queries, future dates, invalid metrics

### 2.3 Update Web API (web/app.py)
- [ ] Modify POST /api/query to check classification
- [ ] Route to GlookoQueryAgent for glooko_data classification
- [ ] Load analysis files from data/analysis/
- [ ] Return structured response with source attribution

### 2.4 Update Web UI (web/index.html)
- [ ] Add "Your Glooko Data" to sources sidebar
- [ ] Add CSS styling for data query results
- [ ] Display metadata (date range, data completeness)

### 2.5 Update Web UI (web/static/app.js)
- [ ] Handle glooko_data source responses
- [ ] Format data queries with special styling (inline stats, tables)
- [ ] Display disclaimers prominently
- [ ] Show data context (date range, sources)

### 2.6 Add Example Questions
- [ ] Update welcome screen with data query examples
- [ ] Examples:
  - "What was my time in range last week?"
  - "When do I typically experience lows?"
  - "How does my glucose trend after meals?"
  - "What's my average glucose?"

### 2.7 Create Tests (tests/test_glooko_query.py)
- [ ] Test temporal filtering
- [ ] Test metric calculations
- [ ] Test pattern detection
- [ ] Test edge cases (no data, future dates, ambiguous queries)
- [ ] Test response formatting

### 2.8 Update Documentation
- [ ] Update WEB_INTERFACE.md with data query examples
- [ ] Update GLOOKO_INTEGRATION.md with query capabilities
- [ ] Add troubleshooting section for no data scenarios

---

## Phase 3: Advanced Features (Optional)

If time permits:

### 3.1 Time-Series Visualization
- Embed simple ASCII charts or base64 images in responses
- Use matplotlib to generate glucose trend charts
- Show comparative visualizations for week-over-week

### 3.2 Comparison Queries
- "Compare my TIR this week vs last week"
- "How did my glucose vary Monday vs Friday?"
- Return side-by-side statistics and delta

### 3.3 Export Results
- Allow users to export query results as CSV
- Include query parameters and timestamp
- Enable local analysis

### 3.4 Proactive Insights
- Analyze patterns continuously
- Offer insights: "I notice your TIR dropped 15% this week"
- Flag concerning trends automatically

---

## Technical Considerations

### Data Structure
Expected analysis JSON structure:
```json
{
  "date": "2026-01-27",
  "readings": [
    {
      "timestamp": "2026-01-27T08:30:00",
      "glucose_mg_dl": 142,
      "glucose_mmol_l": 7.9,
      "type": "reading|meal|exercise|insulin",
      "meal_carbs": 45,
      "exercise_duration": 30,
      "exercise_type": "running"
    }
  ],
  "daily_summary": {
    "average_glucose": 142,
    "time_in_range_percent": 68,
    "readings_count": 127
  }
}
```

### Performance Considerations
- Cache analysis files in memory (they're static once uploaded)
- Use pandas for efficient filtering and aggregation
- Limit date range queries to 6 months to avoid performance issues
- Index data by date for faster filtering

### Safety and Privacy
- All data queries stay within the user's session
- Data never sent to external APIs for personal metrics
- Only use Gemini for query interpretation (intent parsing), not data access
- Include disclaimers on all responses
- Track which fields user has data for (don't claim missing fields exist)

### Error Handling
- **No data uploaded:** "No Glooko data found. Please upload your export file first."
- **No data for range:** "No readings found for Jan 1-5. Your data starts from Jan 10."
- **Ambiguous query:** "I'm not sure which metric you're asking about. Did you mean average glucose or time in range?"
- **Future date:** "I can't query future dates. Your latest data is from Jan 27, 2026."

---

## Success Criteria

✅ Users can ask natural language questions about their diabetes data
✅ Questions are correctly classified and routed to GlookoQueryAgent
✅ Answers include appropriate context (date range, units, disclaimers)
✅ All responses pass Safety Auditor review
✅ Edge cases handled gracefully with helpful error messages
✅ Multi-agent architecture remains intact and unmodified
✅ Existing chat functionality unchanged

---

## Timeline Estimate

| Phase | Task | Estimated Time |
|-------|------|-----------------|
| 1 | Architecture document | Complete ✅ |
| 2.1 | Update Triage Agent | 30-45 min |
| 2.2 | Create GlookoQueryAgent | 1-1.5 hrs |
| 2.3 | Update Web API | 20-30 min |
| 2.4-2.5 | Update Web UI | 45-60 min |
| 2.6 | Example questions | 15 min |
| 2.7 | Write tests | 45-60 min |
| 2.8 | Update docs | 30-45 min |
| **Phase 2 Total** | | **4-5 hours** |
| 3 | Advanced features | 2-3 hrs (optional) |

---
