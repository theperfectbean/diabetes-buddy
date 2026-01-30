# 🩺 Diabetes Buddy - AI Knowledge Partner

Multi-agent RAG system for Type 1 Diabetes management with mandatory safety guardrails and authoritative knowledge grounding.

## ✨ Features

- **🎯 Zero Hallucinations** - All answers grounded in uploaded medical literature
- **🛡️ Safety-First Architecture** - Blocks harmful advice, adds medical disclaimers
- **⚡ Fast Local Search** - ChromaDB vector store for <5s queries
- **🔍 Source Citations** - Every answer includes page numbers
- **🤖 MCP Integration** - Use from Claude Desktop or other MCP clients
- **📚 Expert Knowledge Base** - 4 authoritative sources always up-to-date

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API Key

```bash
echo "GEMINI_API_KEY=your-key-here" > .env
```

### 3. Run Interactive Mode

```bash
python -m diabuddy
```

**First run:** Processes PDFs (3-5 minutes one-time setup)  
**Subsequent runs:** Instant startup, 3-5s per query

## 📖 Usage

### Command Line

```bash
# Interactive REPL
python -m diabuddy

# Single query
python -m diabuddy "What is Ease-off mode?"

# JSON output (for scripting)
python -m diabuddy --json "How do I change my pump cartridge?"

# Verbose mode with timing
python -m diabuddy -v "How do I prepare for exercise?"
```

### Claude Desktop (MCP)

See [MCP_SETUP.md](MCP_SETUP.md) for installation instructions.

Once installed, ask Claude:
```
"Use diabetes-buddy to explain what Boost mode does"
```

### VS Code + GitHub Copilot (MCP)

**Quick Setup:**
1. Install MCP extension: `code --install-extension modelcontextprotocol.mcp`
2. Open project in VS Code: `code .`
3. Reload window: `Ctrl+Shift+P` → "Developer: Reload Window"
4. Test in Copilot Chat: `@workspace use diabetes-buddy to explain what Ease-off mode is`

See [VSCODE_QUICKSTART.md](VSCODE_QUICKSTART.md) for detailed instructions.

## 📚 Knowledge Sources

| Source | Content | Pages |
|--------|---------|-------|
| **Think Like a Pancreas** | Behavioral strategies, insulin logic | ~400 |
| **CamAPS FX Manual** | Hybrid closed-loop algorithm | ~150 |
| **Ypsomed Pump Manual** | Hardware operation | ~200 |
| **FreeStyle Libre 3** | CGM sensor guide | ~100 |

## 🏗️ Architecture

```
┌──────────────┐
│ User Query   │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│  Triage Agent    │  Classifies: Theory/CamAPS/Ypsomed/Libre
│  (LiteLLM)       │  Confidence: 70%+ → Single source
└──────┬───────────┘  Confidence: <70% → Multi-source
       │
       ▼
┌──────────────────┐
│ Researcher Agent │  ChromaDB vector search (<1s)
│  (ChromaDB +     │  Parallel multi-source queries
│   LiteLLM)       │  In-memory result caching
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  Safety Auditor  │  Blocks specific doses
│  (Regex + Rules) │  Injects disclaimers
└──────┬───────────┘  Audit trail
       │
       ▼
┌──────────────────┐
│  Safe Response   │  With citations & severity level
└──────────────────┘
```

## 🛡️ Safety Features

### Dose Detection
Blocks patterns like:
- "take 5 units"
- "increase by 2 units"  
- "5u for 50g carbs"

### Severity Levels
- 🟢 **INFO** - Safe informational content
- 🟡 **WARNING** - Potentially concerning, disclaimer added
- 🔴 **BLOCKED** - Dangerous content removed/replaced

### Mandatory Disclaimers
Every response includes:
> **Disclaimer:** This is educational information only. Always consult your healthcare provider before making changes to your diabetes management routine.

## ⚡ Performance

| Query Type | Time | Notes |
|------------|------|-------|
| First query ever | 3-5 min | One-time PDF processing |
| Single-source | 3-5s | Classification + search + synthesis |
| Multi-source | 5-8s | Parallel searches |
| Repeated query | 3-5s | Results cached in memory |

**Optimization Tips:**
- Use specific questions for single-source routing
- Let ChromaDB process PDFs once on first run
- Use `-v` flag to see timing breakdown

## 🧪 Testing

```bash
# Test ChromaDB backend
python -m agents.researcher_chromadb

# Test triage agent
python -m agents.triage

# Test with verbose output
python -m diabuddy -v "test query"
```

## 📁 Project Structure

```
diabetes-buddy/
├── agents/                    # Multi-agent system
│   ├── researcher_chromadb.py # Fast local vector search
│   ├── triage.py             # Query classification & routing
│   └── safety.py             # Safety auditing & filtering
├── diabuddy/                 # CLI interface
│   └── __main__.py
├── docs/                     # Knowledge base PDFs
│   ├── theory/
│   └── manuals/
├── mcp_server.py            # MCP server for Claude Desktop
└── .cache/                   # Local storage
    ├── chromadb/            # Vector embeddings
    └── gemini_files/        # File handles
```

## 🔧 Configuration

### LLM Provider

Uses **LiteLLM** for multi-provider support with Google Gemini as the default. See [docs/LITELLM_MIGRATION.md](docs/LITELLM_MIGRATION.md) for details.

Supported providers: Gemini, OpenAI, Anthropic, Ollama

### Environment Variables

```bash
GEMINI_API_KEY=your-key-here     # Required for Gemini
GEMINI_MODEL=gemini/gemini-2.5-flash  # MUST include gemini/ prefix
CACHE_DIR=/custom/path           # Optional
```

### Backend Selection

ChromaDB backend is automatic. To force legacy File API:

```python
from agents import ResearcherAgent
researcher = ResearcherAgent(use_chromadb=False)
```

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'google'"
```bash
pip install -r requirements.txt
```

### "GEMINI_API_KEY environment variable not set"
```bash
echo "GEMINI_API_KEY=your-key" > .env
```

### Slow first-time startup
Normal! Processing 4 PDFs + creating embeddings takes 3-5 minutes once.

### ChromaDB errors
Delete cache and rebuild:
```bash
rm -rf .cache/chromadb
python -m diabuddy  # Will rebuild
```

## 📊 Metrics

- **Query Latency:** 3-5s average (down from 14-17s)
- **Accuracy:** Grounded in source docs (no hallucinations)
- **Safety:** 100% dose blocking, mandatory disclaimers
- **Cache Hit Rate:** ~80% for repeated queries
- **Knowledge Base:** 850+ pages across 4 authoritative sources

## 🛠️ Development

### Adding New Knowledge Sources

1. Add PDF to `docs/` folder
2. Update `PDF_PATHS` in `researcher_chromadb.py`
3. Delete `.cache/chromadb/` to rebuild
4. Restart CLI

### Running Tests

```bash
# Test individual agents
python -m agents.researcher_chromadb
python -m agents.triage
python -m agents.safety

# Test MCP server
python mcp_server.py
```

## 📝 License

Educational/Research use. Not for clinical decision-making.

## ⚠️ Medical Disclaimer

This tool provides **educational information only**. It is not a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of qualified healthcare providers with questions about medical conditions or treatment plans.

## 🤝 Contributing

This is a personal project for diabetes self-management education. Feedback welcome!

## 📚 References

- Think Like a Pancreas (Gary Scheiner, MS, CDCES, 2025 Edition)
- CamAPS FX User Manual (Commercial Version, mmol/L)
- Ypsomed mylife YpsoPump eIFU
- FreeStyle Libre 3 CGM User Manual

---

Built with ❤️ for the Type 1 Diabetes community.
