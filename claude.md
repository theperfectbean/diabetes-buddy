# Diabetes Buddy - Agentic Knowledge Partner

## Project Overview
Multi-agent system for Type 1 Diabetes management using Retrieval-Augmented Generation (RAG). Acts as a specialized cognitive assistant grounded in clinical theory and technical manuals.

## Core Mission
Provide expert-level diabetes guidance without hallucinations by synthesizing three authoritative knowledge sources with a multi-agent architecture that includes mandatory safety guardrails.

## Knowledge Sources (Three Pillars)
1. **Behavioral Strategy**: "Think Like a Pancreas" by Gary Scheiner - Real-world insulin logic
2. **Mechanical Logic**: mylife Ypsomed Pump Manual - Hardware-specific procedures
3. **Algorithmic Logic**: CamAPS FX User Guide - Hybrid closed-loop system behavior

## Technical Stack
- **Platform**: Debian Linux (Bash)
- **Language**: Python 3.x
- **AI SDK**: google-generativeai (Gemini)
- **Protocols**: Model Context Protocol (MCP) for secure local file access
- **RAG Framework**: LangChain + ChromaDB
- **Version Control**: Git + GitHub

## Agent Architecture
Three specialized agents work in sequence:

### 1. Triage Agent (Router)
- Classifies queries into: Theory, Hardware, Algorithm, or Hybrid
- Routes to appropriate knowledge sources
- Located: `agents/triage.py`

### 2. Researcher Agent (RAG)
- Performs retrieval-augmented generation from PDFs
- Extracts exact quotes and procedures
- Provides context-aware responses
- Located: `agents/researcher.py`

### 3. Safety Auditor (Gatekeeper)
- **NON-NEGOTIABLE LAYER**
- Blocks specific insulin dosage recommendations
- Injects medical disclaimers on all outputs
- Prevents harmful advice
- Located: `agents/safety.py`

## Safety Requirements (CRITICAL)
- ❌ NEVER provide specific insulin doses (e.g., "take 3 units")
- ✅ ALWAYS include disclaimer: "This is educational information. Consult your healthcare provider."
- ✅ Suggest strategies, timing, and mode adjustments only
- ✅ Reference equipment manuals for technical procedures

## Development Workflow
1. All code edits use heredoc format
2. One step at a time with user confirmation
3. Provide copy-paste commands always
4. Test each agent independently before integration

## File Structure
diabetes-buddy/
├── claude.md # This file
├── .env # API keys (not committed)
├── .gitignore # Git exclusions
├── requirements.txt # Python dependencies
├── agents/ # Agent modules
│ ├── triage.py
│ ├── researcher.py
│ └── safety.py
├── docs/ # Knowledge source PDFs
│ ├── think_like_pancreas.pdf
│ ├── ypsomed_manual.pdf
│ └── camaps_guide.pdf
├── config/ # Configuration files
│ └── mcp_config.json
└── tests/ # Unit tests
├── test_triage.py
├── test_researcher.py
└── test_safety.py

text

## Next Steps
1. Add knowledge source PDFs to `docs/` folder
2. Configure Google GenAI API key in `.env`
3. Build Triage Agent first
4. Build Researcher Agent with RAG pipeline
5. Build Safety Auditor last
6. Integration testing with all three agents

## Code Style
- Use type hints
- Docstrings for all functions
- Async/await for agent coordination
- Error handling for all external calls
