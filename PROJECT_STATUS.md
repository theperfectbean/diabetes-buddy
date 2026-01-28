# Diabetes Buddy - Project Status
**Last Updated:** 2026-01-26

## Completed

### Infrastructure
- Python 3.12.8 venv with google-genai SDK
- Git repository initialized
- IPv4 network fix (`agents/network.py`) - fixes Google API timeouts
- GEMINI_API_KEY configured (upgraded from free tier)
- **NEW:** Upgraded to Gemini 2.5 Flash for improved performance

### Knowledge Base (docs/)
- `docs/theory/` - Think Like a Pancreas (Gary Scheiner, 2025 edition)
- `docs/manuals/algorithm/` - CamAPS FX user manual (mmol/L)
- `docs/manuals/hardware/` - Ypsomed pump eIFU
- `docs/manuals/hardware/` - FreeStyle Libre 3 CGM manual

### Agents (All 3 Core Agents Complete)

#### 1. RAG Researcher Agent (`agents/researcher_chromadb.py`)
**NEW:** ChromaDB-based local vector search replacing slow Gemini File API.
- One-time PDF processing (~3-5 minutes) creates local embeddings
- Fast semantic search using ChromaDB (<1s retrieval)
- Parallel multi-source queries with ThreadPoolExecutor
- In-memory result caching for repeated queries
- Automatic fallback to legacy File API if needed

**Performance:** 13s → 3-5s per query (60-75% faster)

#### 2. Triage Agent (`agents/triage.py`)
Query classification and routing to appropriate knowledge sources.
- Smart synthesis with optimized prompts
- Parallel search execution for multi-source queries
- Timing instrumentation (use `-v` flag)

#### 3. Safety Auditor (`agents/safety.py`)
Gatekeeper with dose detection, warnings, and mandatory disclaimers.

### CLI Interface (`diabuddy/`)

Interactive and single-query command-line interface.

**Usage:**
```bash
# Interactive REPL mode
python -m diabuddy

# Single query
python -m diabuddy "How do I change my pump cartridge?"

# JSON output (for scripting)
python -m diabuddy --json "What is Ease-off mode?"

# Verbose mode
python -m diabuddy -v "How do I prepare for exercise?"
```

**Interactive Commands:**
- `/help` - Show help
- `/sources` - List knowledge sources
- `/audit` - Show session audit summary
- `/quit` - Exit

**Features:**
- Color-coded severity levels (green=INFO, yellow=WARNING, red=BLOCKED)
- Source citations with page numbers
- Safety audit status on every response
- Session summary on exit
- **NEW:** Performance timing with `-v` flag
- **NEW:** ChromaDB backend for fast retrieval

**Example Output:**
```
[YPSOMED] (95% confidence)
Safety: INFO

------------------------------------------------------------
To change your pump cartridge on a mylife YpsoPump, follow these steps...
(Ypsomed Pump Manual, Page 91)

---
**Disclaimer:** This is educational information only. Always consult
your healthcare provider before making changes to your diabetes
management routine.
```

### Web Interface (`web/`) ✅ IMPROVED

Full-featured web chat interface with FastAPI backend.

**New Features (v1.1):**
- **Dark Mode** - Toggle with moon/sun icon, persists preference
- **Conversation History** - Persists in localStorage (last 50 messages)
- **Export** - Download chat as text or JSON
- **Copy to Clipboard** - Copy button on each response
- **Suggested Questions** - Welcome screen with example queries
- **Skeleton Loading** - Animated loading states
- **Accessibility** - ARIA labels, keyboard nav, focus trap, colorblind-friendly

**Security & Reliability:**
- Input validation (3-2000 chars)
- Rate limiting (10 req/min per IP)
- CORS configuration
- Retry logic with exponential backoff
- Proper error messages

**API Endpoints:**
- `POST /api/query` - Ask questions (with validation & rate limiting)
- `GET /api/sources` - List knowledge sources
- `GET /api/health` - Health check with agent status
- `GET /docs` - Swagger UI documentation
- `GET /redoc` - ReDoc documentation

See [WEB_INTERFACE.md](WEB_INTERFACE.md) for full documentation.

### Docker Support ✅ NEW

Containerized deployment for easy sharing and production use.

**Files:**
- `Dockerfile` - Multi-stage build (~900MB final image)
- `docker-compose.yml` - Easy local development
- `.dockerignore` - Optimized build context

**Quick Start:**
```bash
cp .env.example .env   # Add your GEMINI_API_KEY
docker compose up -d
# Open http://localhost:8000
```

See [DOCKER.md](DOCKER.md) for full documentation.

### MCP Server (`mcp_server.py`) ✅ NEW

Model Context Protocol server for IDE/editor integration.

**Supported Clients:**
- ✅ VS Code + GitHub Copilot (Chromebook compatible!)
- ✅ Claude Desktop (macOS/Windows/Linux)
- ✅ Any MCP-compatible client

**Installation:**
- **VS Code**: See [VSCODE_QUICKSTART.md](VSCODE_QUICKSTART.md) - 5 minute setup
- **Claude Desktop**: See [MCP_SETUP.md](MCP_SETUP.md) - Full guide

**Tools Exposed:**
- `diabetes_query` - Ask questions with full safety auditing
- `search_theory`, `search_camaps`, `search_ypsomed`, `search_libre` - Direct source searches
- `get_knowledge_sources` - List available sources

**VS Code Usage:**
```
@workspace use diabetes-buddy to explain what Ease-off mode is
```

## Performance Improvements
```
diabetes-buddy/
├── agents/
│   ├── __init__.py          # Module exports
│   ├── network.py           # IPv4 fix for Google APIs
│   ├── researcher.py        # Legacy File API backend
│   ├── researcher_chromadb.py  # NEW: ChromaDB backend (fast!)
│   ├── triage.py            # Triage Agent (with parallel search)
│   └── safety.py            # Safety Auditor Agent
├── diabuddy/
│   ├── __init__.py          # Package info
│   └── __main__.py          # CLI entry point (with timing)
├── docs/
│   ├── theory/              # Think Like a Pancreas PDF
│   └── manuals/
│       ├── algorithm/       # CamAPS FX manual
│       └── hardware/        # Ypsomed + Libre 3 manuals
├── .cache/
│   ├── gemini_files/        # Cached Gemini file handles
│   └── chromadb/            # NEW: ChromaDB vector store
├── .vscode/
│   └── settings.json        # NEW: VS Code MCP configuration
├── mcp_server.py            # NEW: MCP server
├── MCP_SETUP.md             # NEW: MCP guide (Claude Desktop)
├── VSCODE_QUICKSTART.md     # NEW: VS Code setup (5 min)
├── claude_desktop_config.json  # NEW: Example config
├── .env                     # API keys (gitignored)
├── requirements.txt         # Python dependencies
└── README.md                # Project documentation
```

## Quick Start (Chromebook/VS Code)

```bash
# 1. Open in VS Code
code /home/gary/diabetes-buddy

# 2. Install MCP extension
code --install-extension modelcontextprotocol.mcp

# 3. Reload VS Code
# Ctrl+Shift+P → "Developer: Reload Window"

# 4. Test in Copilot Chat
@workspace use diabetes-buddy to explain what Ease-off mode is
```

See [VSCODE_QUICKSTART.md](VSCODE_QUICKSTART.md) for details.
├── claude_desktop_config.json  # NEW: Example config
├── .env                     # API keys (gitignored)
├── requirements.txt         # Python dependencies
└── claude.md                # Project specification
```

## Quick Start
```bash
# Activate virtual environment
source venv/bin/activate

# Run interactive mode
python -m diabuddy

# Or ask a single question
python -m diabuddy "How do I calculate my insulin to carb ratio?"
```
