# Diabetes Buddy - Architecture Overview

**Multi-Agent RAG System for Type 1 Diabetes Management**

Version: 2.0  
Last Updated: February 3, 2026

---

## 🎯 System Overview

Diabetes Buddy is a **safety-first, knowledge-grounded AI assistant** for Type 1 Diabetes management. The system combines:

- **Multiple specialized AI agents** working in coordination
- **Retrieval-Augmented Generation (RAG)** for fact-based answers
- **Personal health data analysis** from Glooko exports
- **Mandatory safety guardrails** to prevent harmful advice
- **Multi-interface access** (CLI, Web UI, MCP server)

### Core Principles

1. **Zero Hallucinations**: All medical advice grounded in authoritative sources
2. **Safety First**: Multi-tier filtering blocks dangerous advice
3. **Source Attribution**: Every answer includes citations with page numbers
4. **Personal Context**: Integrates user's glucose data when available
5. **Device Awareness**: Tailors advice to user's insulin pump/CGM system

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Interfaces                         │
├─────────────┬─────────────────┬──────────────────┬──────────────┤
│   CLI       │    Web UI       │   MCP Server     │  REST API    │
│  (REPL)     │  (FastAPI)      │  (Claude Desktop)│              │
└──────┬──────┴────────┬────────┴──────────┬───────┴──────┬───────┘
       │               │                   │              │
       └───────────────┴───────────────────┴──────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │   Unified Agent     │
                    │  (Query Orchestrator)│
                    └─────────┬───────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌────────────────┐  ┌────────────────┐  ┌─────────────────┐
│ Safety Auditor │  │ Triage Agent   │  │ Session Manager │
│ (Pre/Post)     │  │ (Query Intent) │  │ (Conversation)  │
└────────────────┘  └────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┴────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌────────────────┐  ┌────────────────┐  ┌─────────────────┐
│   Researcher   │  │  Glooko Query  │  │ Device Manager  │
│  (Knowledge    │  │  (User Data    │  │ (Pump/CGM      │
│   Base RAG)    │  │   Analysis)    │  │  Detection)    │
└────────┬───────┘  └────────┬───────┘  └─────────────────┘
         │                   │
         ▼                   ▼
┌────────────────┐  ┌────────────────┐
│   ChromaDB     │  │  Glooko JSON   │
│  Vector Store  │  │   (User Data)  │
└────────────────┘  └────────────────┘
```

---

## 🧩 Core Components

### 1. **Unified Agent** (`agents/unified_agent.py`)

**Role**: Central orchestrator that coordinates all other agents

**Responsibilities**:
- Receives natural language queries
- Coordinates knowledge retrieval + personal data analysis
- Manages conversation context
- Applies safety filtering
- Generates comprehensive responses
- Handles A/B testing experiments

**Key Features**:
- **Hybrid System**: Always retrieves both knowledge base + Glooko data
- **LLM Decision-Making**: Lets the LLM decide what's relevant
- **RAG Quality Assessment**: Evaluates retrieval quality to decide between pure RAG vs. hybrid modes
- **Device Personalization**: Tailors responses based on user's pump/CGM

**Flow**:
```python
query → device detection → parallel retrieval:
  ├─ Knowledge base (ResearcherAgent)
  └─ User data (GlookoQueryAgent)
→ LLM synthesis → safety audit → response
```

### 2. **Researcher Agent** (`agents/researcher_chromadb.py`)

**Role**: Knowledge base retrieval using vector search

**Responsibilities**:
- Semantic search over medical literature
- Multi-query expansion for comprehensive coverage
- Hybrid search (vector + keyword)
- Source attribution with page numbers
- Confidence scoring

**Data Sources** (in `data/knowledge/`):
- OpenAPS Documentation (diabetes management protocols)
- Tandem t:slim X2 User Guide (insulin pump manual)
- Dexcom G7 User Guide (CGM system manual)
- PubMed papers (research literature)

**Technology**:
- **ChromaDB**: Vector database for embeddings
- **Gemini Embeddings**: `text-embedding-004` model
- **Hybrid Retrieval**: Combines semantic + lexical search
- **Reranking**: Improves relevance of top results

### 3. **Glooko Query Agent** (`agents/glooko_query.py`)

**Role**: Personal diabetes data analysis

**Responsibilities**:
- Parses natural language queries about user's data
- Queries Glooko export JSON files
- Calculates glucose metrics (averages, TIR, patterns)
- Generates time series and trend analysis
- Provides context-aware summaries

**Supported Queries**:
- Time in Range (TIR): "What's my TIR this week?"
- Averages: "What was my average glucose yesterday?"
- Patterns: "When do I have most lows?"
- Trends: "Is my control improving?"
- Events: "How many highs did I have last month?"

**Data Format**: Processes Glooko JSON exports containing:
- CGM glucose readings
- Insulin pump data (basal/bolus)
- Exercise logs
- Carbohydrate intake

### 4. **Safety Auditor** (`agents/safety.py`)

**Role**: Multi-tier safety filtering system

**Responsibilities**:
- **Pre-query filtering**: Blocks dangerous queries before processing
- **Post-response filtering**: Scans generated responses for harmful advice
- **Pattern detection**: Recognizes unsafe medication changes, dosing advice
- **Severity classification**: Categorizes issues (CRITICAL, HIGH, MEDIUM, LOW)
- **Auto-correction**: Adds disclaimers and safety warnings

**Safety Tiers**:

| Tier | Scope | Examples |
|------|-------|----------|
| **CRITICAL** | Life-threatening | "Stop insulin", "Skip meals", "Ignore alarms" |
| **HIGH** | Medical changes | Specific dosing advice, pump settings changes |
| **MEDIUM** | General advice | Exercise timing, carb counting tips |
| **LOW** | Informational | Device features, data interpretation |

**Enforcement**:
- CRITICAL: Query blocked, error message returned
- HIGH: Response filtered + mandatory disclaimer added
- MEDIUM/LOW: Allowed with context-appropriate disclaimers

### 5. **Triage Agent** (`agents/triage.py`)

**Role**: Query classification and intent detection

**Responsibilities**:
- Classifies queries into categories (knowledge, data, mixed, general)
- Detects safety concerns early
- Determines query complexity
- Routes to appropriate processing pipeline

**Categories**:
- **KNOWLEDGE_ONLY**: Questions about diabetes management concepts
- **DATA_ONLY**: Questions about user's personal data
- **MIXED**: Requires both knowledge + personal data
- **GENERAL_CHAT**: Off-topic or conversational

### 6. **Device Manager** (`agents/device_detection.py`)

**Role**: Detects user's diabetes devices (pump, CGM) and personalizes responses

**Responsibilities**:
- Analyzes Glooko data to identify insulin pump and CGM models
- Maintains device profiles with capabilities and terminology
- Provides device-specific context to UnifiedAgent
- Enables tailored responses (e.g., "Control-IQ" vs. "Loop")

**Supported Devices**:
- **Pumps**: Tandem t:slim X2, Medtronic, Omnipod
- **CGMs**: Dexcom G6/G7, Libre, Medtronic Guardian

### 7. **Session Manager** (`agents/session_manager.py`)

**Role**: Conversation history and context management

**Responsibilities**:
- Creates unique session IDs
- Persists conversation history to disk
- Loads previous conversations
- Provides conversation context for follow-up queries

**Storage**: JSON files in `data/sessions/`

### 8. **LLM Provider** (`agents/llm_provider.py`)

**Role**: Abstraction layer for multiple LLM backends

**Responsibilities**:
- Unified interface for different LLM providers
- Configurable generation parameters (temperature, max tokens)
- Retry logic with exponential backoff
- Cost tracking and logging

**Supported Models**:
- **Gemini**: `gemini-2.0-flash-exp`, `gemini-1.5-pro`
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`
- **Anthropic**: `claude-3-5-sonnet`, `claude-3-opus`
- **Local**: Ollama models

### 9. **Experimentation System** (`agents/experimentation.py`)

**Role**: A/B testing framework for model/prompt evaluation

**Responsibilities**:
- Cohort assignment (treatment vs. control)
- Variant tracking (model, prompts, RAG strategies)
- Analytics collection (latency, token usage, user feedback)
- Statistical significance testing

**Use Cases**:
- Compare Gemini vs. GPT-4o performance
- Test different RAG retrieval strategies
- Evaluate prompt engineering changes

---

## 🔄 Query Processing Flow

### Standard Query Lifecycle

```
1. User Input
   ↓
2. Triage (classify intent, detect safety issues)
   ↓
3. Device Detection (identify pump/CGM from Glooko data)
   ↓
4. Safety Pre-filtering (block critical safety violations)
   ↓
5. Parallel Retrieval:
   ├─ Researcher: Knowledge base search (ChromaDB)
   └─ Glooko: User data analysis
   ↓
6. LLM Synthesis (combine knowledge + data + conversation context)
   ↓
7. Safety Post-filtering (scan response for unsafe advice)
   ↓
8. Session Storage (save conversation)
   ↓
9. Response Delivery (with sources, disclaimers, metrics)
```

### Hybrid Knowledge System

The system uses **adaptive retrieval quality assessment**:

```python
if rag_quality.is_sufficient():
    # Pure RAG mode: Trust knowledge base
    response = generate_from_knowledge_only()
else:
    # Hybrid mode: Knowledge base + web search fallback
    response = generate_with_hybrid_sources()
```

**RAG Quality Metrics**:
- Chunk count (minimum 3 for sufficiency)
- Average confidence score (>0.7)
- Source diversity (multiple documents)
- Topic coverage assessment

---

## 🌐 Interface Layer

### 1. **Web UI** (`web/app.py`)

**Technology**: FastAPI + vanilla JavaScript

**Features**:
- Real-time streaming responses (Server-Sent Events)
- Conversation history sidebar
- Glooko data upload (drag-and-drop)
- Session management
- Device detection display
- Rate limiting (10 requests/minute)
- Analytics dashboard

**Endpoints**:
- `POST /api/query` - Submit query, get streaming response
- `GET /api/sessions` - List conversation sessions
- `GET /api/session/{id}` - Retrieve session history
- `POST /api/upload` - Upload Glooko export
- `GET /api/analytics` - Experiment analytics
- `GET /api/device-info` - User's detected devices

### 2. **MCP Server** (`mcp_server.py`)

**Technology**: Model Context Protocol (MCP)

**Purpose**: Expose Diabetes Buddy as tools for Claude Desktop

**Tools Exposed**:
- `query_diabetes_knowledge`: Ask diabetes management questions
- `safety_audit`: Check if a question/answer is safe

**Usage**: Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "diabetes-buddy": {
      "command": "python",
      "args": ["/path/to/diabetes-buddy/mcp_server.py"]
    }
  }
}
```

### 3. **CLI Interface** (`diabuddy/__main__.py`)

**Modes**:
- **Interactive REPL**: `python -m diabuddy`
- **Single query**: `python -m diabuddy "query here"`
- **JSON output**: `python -m diabuddy --json "query"`

**Features**:
- Session persistence
- Source citations
- Colored output (rich library)
- Conversation history

---

## 💾 Data Storage

### Directory Structure

```
data/
├── knowledge/           # Medical literature (PDFs)
│   ├── OpenAPS-reference-design.pdf
│   ├── Tandem_tslimX2_UserGuide.pdf
│   ├── Dexcom_G7_UserGuide.pdf
│   └── pubmed/         # Research papers
├── glooko/             # User-uploaded Glooko exports
│   └── {user_id}/
│       ├── latest.json
│       └── uploads/
├── sessions/           # Conversation history
│   └── {session_id}.json
├── users/              # User profiles
│   └── {user_id}/
│       ├── profile.json
│       └── devices.json
├── chroma_db/          # ChromaDB vector store
└── cache/              # Temporary files
```

### ChromaDB Collections

- `diabetes_knowledge`: Main knowledge base
  - Embeddings: Gemini `text-embedding-004`
  - Metadata: source, page, chunk_id, doc_type
  - Distance metric: Cosine similarity

### Session Format

```json
{
  "session_id": "uuid",
  "user_id": "optional",
  "created_at": "ISO8601",
  "messages": [
    {
      "role": "user",
      "content": "query",
      "timestamp": "ISO8601"
    },
    {
      "role": "assistant",
      "content": "response",
      "timestamp": "ISO8601",
      "metadata": {
        "sources": [...],
        "safety_level": "MEDIUM",
        "processing_time_ms": 3421,
        "model_used": "gemini-2.0-flash-exp"
      }
    }
  ]
}
```

---

## 🛡️ Safety Architecture

### Multi-Layer Defense

```
Layer 1: Query Pre-filtering
  ↓ (Blocks CRITICAL safety violations)
  
Layer 2: Response Generation
  ↓ (Grounded in authoritative sources)
  
Layer 3: Response Post-filtering
  ↓ (Scans for unsafe patterns)
  
Layer 4: Disclaimer Injection
  ↓ (Adds medical disclaimers)
  
Layer 5: Audit Logging
  ↓ (Records safety events)
```

### Safety Patterns Detected

**Dangerous Insulin Changes**:
- "Stop/skip your insulin"
- "Double/halve your doses"
- "Change your basal rates to..."

**Dangerous Glucose Management**:
- "Ignore your alarms"
- "Let your glucose go to X"
- "Skip meals to lower glucose"

**Medical Decision Override**:
- "Don't listen to your doctor"
- "You don't need to test"
- "Stop using your pump"

### Enforcement Mechanism

```python
if severity == Severity.CRITICAL:
    return error_response("Query blocked for safety")
elif severity == Severity.HIGH:
    response += safety_disclaimer()
    log_safety_event()
elif severity == Severity.MEDIUM:
    response += general_disclaimer()
```

---

## 🔧 Configuration

### Main Config (`config/hybrid_knowledge.yaml`)

```yaml
rag:
  quality_thresholds:
    min_chunks: 3
    min_avg_confidence: 0.7
  retrieval:
    top_k: 10
    rerank: true

hybrid:
  fallback_enabled: true
  web_search_trigger: low_rag_quality

logging:
  level: INFO
  file_path: logs/hybrid_system.log
  max_size_mb: 10

llm:
  default_provider: gemini
  default_model: gemini-2.0-flash-exp
  temperature: 0.1
  max_tokens: 2048
```

### Model Config (`config/models.json`)

Defines available LLM models, API endpoints, and pricing.

### User Profile (`config/user_profile.json`)

```json
{
  "user_id": "uuid",
  "devices": {
    "pump": "Tandem t:slim X2",
    "cgm": "Dexcom G7"
  },
  "preferences": {
    "glucose_units": "mg/dL",
    "carb_ratio": "1:10",
    "correction_factor": "1:50"
  },
  "experiment_cohort": "treatment_a"
}
```

---

## 📊 Analytics & Monitoring

### Metrics Collected

- **Performance**: Query latency, token usage, cost per query
- **Quality**: RAG confidence scores, source diversity
- **Safety**: Safety violation counts by severity
- **Usage**: Queries per session, conversation length
- **Experiments**: Cohort performance, A/B test results

### Analytics Dashboard

Access at `/analytics` in web UI:
- Experiment results visualization
- Model performance comparison
- Safety event trends
- User engagement metrics

---

## 🚀 Deployment Options

### 1. Local Development

```bash
python -m diabuddy  # CLI mode
python web/app.py   # Web UI (http://localhost:8000)
```

### 2. Docker

```bash
docker-compose up
```

Services:
- **app**: FastAPI web server (port 8000)
- **chromadb**: Vector database (port 8001)

### 3. Production (Future)

- Kubernetes deployment
- Redis for session management
- PostgreSQL for analytics
- Load balancing for multiple replicas

---

## 🔐 Security Considerations

### Data Privacy

- **No cloud upload**: All data stays local
- **Session isolation**: User data segregated by user_id
- **File permissions**: Restricted access to `data/` directory

### API Security

- **Rate limiting**: 10 requests/minute per IP
- **Input validation**: Pydantic models for all inputs
- **CORS restrictions**: Configurable allowed origins
- **File size limits**: Max 50MB for Glooko uploads

### Safety

- **Mandatory auditing**: All responses pass safety checks
- **Logging**: All safety events logged for review
- **Fail-safe**: System blocks on safety errors rather than allowing

---

## 🧪 Testing

### Test Coverage

```
tests/
├── test_safety_patterns.py      # Safety filter tests
├── test_device_priority.py      # Device detection tests
├── test_comprehensive.py        # End-to-end tests
├── test_web_query.py           # Web API tests
└── test_units_pattern.py       # Glucose unit conversion tests
```

### Running Tests

```bash
cd ~/diabetes-buddy
source venv/bin/activate
pytest tests/ -v
```

### Test Categories

1. **Unit Tests**: Individual agent functionality
2. **Integration Tests**: Multi-agent workflows
3. **Safety Tests**: Adversarial safety filter testing
4. **Performance Tests**: Query latency benchmarks

---

## 🛠️ Technology Stack

### Backend
- **Python 3.10+**
- **FastAPI**: Web framework
- **ChromaDB**: Vector database
- **LiteLLM**: Multi-provider LLM interface
- **Pydantic**: Data validation
- **PyYAML**: Configuration management

### AI/ML
- **Gemini API**: Primary LLM + embeddings
- **OpenAI API**: Alternative LLM
- **Anthropic API**: Alternative LLM
- **RAG**: Retrieval-Augmented Generation

### Frontend
- **Vanilla JavaScript**: No framework dependencies
- **Server-Sent Events (SSE)**: Real-time streaming
- **Tailwind CSS**: Styling

### Data Storage
- **ChromaDB**: Vector embeddings
- **JSON files**: Sessions, user profiles, Glooko data
- **SQLite** (via ChromaDB): Metadata storage

### DevOps
- **Docker**: Containerization
- **Docker Compose**: Multi-container orchestration
- **pytest**: Testing framework
- **Ruff**: Linting

---

## 📈 Roadmap & Future Enhancements

### Near-Term
- [ ] PostgreSQL backend for sessions/analytics
- [ ] Redis caching for faster responses
- [ ] Mobile app (React Native)
- [ ] Email/SMS alerts for safety events

### Medium-Term
- [ ] Multi-user authentication (OAuth)
- [ ] Real-time Glooko API integration
- [ ] Voice interface (Whisper integration)
- [ ] Automated report generation

### Long-Term
- [ ] FDA approval pathway exploration
- [ ] Clinical validation studies
- [ ] Healthcare provider dashboard
- [ ] Integration with EHR systems

---

## 📚 Key Documentation

- [README.md](../README.md) - Quick start guide
- [CONFIGURATION.md](CONFIGURATION.md) - Detailed config reference
- [KNOWLEDGE_BASE_SYSTEM.md](KNOWLEDGE_BASE_SYSTEM.md) - RAG implementation
- [GLOOKO_INTEGRATION.md](GLOOKO_INTEGRATION.md) - Personal data analysis
- [EXPERIMENTATION.md](EXPERIMENTATION.md) - A/B testing framework
- [LITELLM_MIGRATION.md](LITELLM_MIGRATION.md) - Multi-LLM support

---

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Code style guidelines
- Branching strategy
- Pull request process
- Testing requirements

---

## 📝 License

See [LICENSE](../LICENSE) for details.

---

## 🙏 Acknowledgments

- **OpenAPS Community**: Open-source diabetes management protocols
- **Tandem Diabetes Care**: Device documentation
- **Dexcom**: CGM system documentation
- **PubMed/NIH**: Medical research access

---

**Maintainer**: gary@diabetesbuddy.local  
**Project**: https://github.com/gary/diabetes-buddy  
**Status**: Active Development
