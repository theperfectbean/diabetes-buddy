# 🩺 Diabetes Buddy - AI Knowledge Partner

Multi-agent RAG system for Type 1 Diabetes management with mandatory safety guardrails and authoritative knowledge grounding.

## ✨ Features

- **🎯 Source-Grounded with Safety Guardrails** - Answers grounded in RAG knowledge base with LLM parametric knowledge blending
- **🛡️ Safety-First Architecture** - Blocks harmful advice, adds medical disclaimers, emergency fallbacks for system failures
- **⚡ Fast Local Search** - ChromaDB vector store for <5s queries
- **🔍 Smart Citations** - Every answer includes source names and confidence scores
- **🤖 MCP Integration** - Use from Claude Desktop or other MCP clients
- **📤 Bring Your Own Sources** - Upload PDFs to customize knowledge base for device-specific advice

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

Diabetes Buddy uses a hybrid approach combining RAG-retrieved sources with LLM parametric knowledge:

- **Tier 1**: ADA Standards of Care 2026 (abstracts via PMC API - auto-updated monthly)
- **Tier 2**: OpenAPS, Loop, AndroidAPS community docs (auto-updated monthly)  
- **Tier 3**: PubMed research, Wikipedia education (auto-updated weekly)

### Bring Your Own Sources

For device-specific advice, upload custom PDFs:
1. Place device manuals (PDF format) in `docs/custom/` folder
2. Update `PDF_PATHS` in `agents/researcher_chromadb.py` to include your sources
3. Delete `.cache/chromadb/` to rebuild the knowledge base
4. Restart the CLI - your device manual is now part of the system

**Examples:** Pump manuals, CGM guides, care plan documents, research papers specific to your diabetes management approach.

### Built-in Sources

| Source | Content | Status |
|--------|---------|--------|
| **ADA Standards** | Clinical recommendations | Auto-updated monthly |
| **OpenAPS Docs** | Loop/Basal algorithm theory | Auto-updated monthly |
| **Loop Docs** | DIY closed-loop setup | Auto-updated monthly |
| **AndroidAPS** | Mobile closed-loop system | Auto-updated monthly |
| **PubMed (via PMC)** | Peer-reviewed research | Auto-updated weekly |
| **Wikipedia** | Educational background | Auto-updated weekly |

## 🏗️ Architecture

```
┌──────────────┐
│ User Query   │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│  Router Agent    │  Content classification + safety check
│  (LiteLLM)       │  Route to appropriate service
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────┐
│  Researcher Agent            │  ChromaDB vector search (<1s)
│  (ChromaDB + LiteLLM)        │  Parallel multi-source queries
└──────┬───────────────────────┘  Source discovery & ranking
       │
       ▼
┌──────────────────────────────┐
│ Hybrid Augmentation          │  Blend RAG-retrieved evidence
│ (RAG + Parametric Knowledge) │  with LLM parametric knowledge
└──────┬───────────────────────┘  when RAG coverage is sparse
       │
       ▼
┌──────────────────┐
│  Safety Auditor  │  Blocks harmful patterns
│  (Rules + LLM)   │  Emergency fallbacks on failures
└──────┬───────────┘  Injects disclaimers & confidence levels
       │
       ▼
┌──────────────────────────────┐
│ Response with Citations      │  Source names & confidence scores
│ & Confidence Metadata        │  Safety severity level
└──────────────────────────────┘
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

### Emergency Fallbacks
When system failures occur on safety-critical queries (e.g., insulin dosing), provides actionable emergency guidance instead of errors:
- Recommends device bolus calculator
- Directs to qualified healthcare provider
- Emergency contacts for critical blood sugar levels

## ⚠️ Known Limitations

### Parametric Knowledge Blending
Responses may include LLM parametric knowledge when RAG coverage is sparse. This is:
- **Controlled**: Safety filters still apply to all content
- **Transparent**: System indicates confidence levels and source availability
- **Intentional**: Better than refusing to answer or providing incomplete information

### Device-Specific Advice
- System provides generic insulin dosing guidance only
- For device-specific advice (pump settings, CGM calibration, etc.), you must upload device manuals to `docs/custom/`
- Without custom sources, device-specific recommendations will be generic and may not apply to your exact hardware

### Safety vs. Completeness
- System prioritizes safety over comprehensiveness
- Some legitimate questions may receive "I'm not confident answering this" responses
- This is intentional to avoid potentially harmful misguidance

### Source Coverage
- Built-in sources focus on T1D management theory and major open-source systems
- Commercial systems (CamAPS, Medtronic, Tandem) require manual PDF uploads
- Regional guidelines may not be represented (upload your local clinical guidelines)

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
CHROMADB_PATH=/custom/chromadb   # ChromaDB storage path (default: .cache/chromadb)
EMBEDDING_MODEL=all-mpnet-base-v2  # Sentence transformer model for embeddings
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

- **Query Latency:** 3-5s average (3-8s for complex multi-source queries)
- **Response Quality:** Grounded in source documents with transparent confidence scoring
- **Safety:** 100% dose blocking, emergency fallbacks for system failures, mandatory disclaimers
- **Cache Hit Rate:** ~80% for repeated queries
- **Knowledge Base:** 850+ pages across 6+ authoritative sources, expandable via custom PDFs

**Note:** Response quality evaluation requires manual review. System aims for helpful, safe responses but all medical advice should be validated by qualified healthcare providers.

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
