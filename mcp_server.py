#!/usr/bin/env python3
"""
MCP Server for Diabetes Buddy

Exposes diabetes knowledge base as tools for Claude Desktop and other MCP clients.
Provides safe, audited access to diabetes management information.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from mcp.server.stdio import stdio_server

from agents import TriageAgent, SafetyAuditor


# Initialize agents globally (reused across requests)
triage_agent = None
safety_auditor = None


def init_agents():
    """Initialize agents on first request."""
    global triage_agent, safety_auditor
    
    if triage_agent is None:
        print("🔧 Initializing Diabetes Buddy agents...", file=sys.stderr)
        triage_agent = TriageAgent()
        safety_auditor = SafetyAuditor(triage_agent=triage_agent)
        print("✅ Agents ready!", file=sys.stderr)


# Create MCP server instance
app = Server("diabetes-buddy")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools for diabetes knowledge queries."""
    return [
        Tool(
            name="diabetes_query",
            description=(
                "Ask a question about diabetes management. "
                "Searches authoritative knowledge sources and returns a safe, audited answer with source citations. "
                "Automatically blocks harmful advice and includes medical disclaimers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The diabetes-related question to answer"
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="get_knowledge_sources",
            description=(
                "List all available knowledge sources with descriptions. "
                "Shows what topics each source covers."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls."""
    
    # Initialize agents if needed
    init_agents()
    
    try:
        if name == "diabetes_query":
            question = arguments.get("question", "")
            if not question:
                return [TextContent(type="text", text="Error: No question provided")]
            
            # Process through safety auditor
            response = safety_auditor.process(question, verbose=False)
            
            # Format response
            triage = response.triage_response
            audit = response.audit
            
            output = []
            
            # Classification info
            if triage:
                output.append(f"**Classification:** {triage.classification.category.value.upper()}")
                output.append(f"**Confidence:** {triage.classification.confidence:.0%}")
                output.append(f"**Reasoning:** {triage.classification.reasoning}\n")
            
            # Safety status
            output.append(f"**Safety Status:** {audit.max_severity.value.upper()}")
            if audit.findings:
                output.append(f"**Safety Findings:** {len(audit.findings)}")
                for f in audit.findings:
                    output.append(f"  - [{f.severity.value}] {f.category}: {f.reason}")
            output.append("")
            
            # Response text
            output.append("**Answer:**")
            output.append(response.response)
            
            return [TextContent(type="text", text="\n".join(output))]
        
        elif name == "get_knowledge_sources":
            # Get dynamic list from ChromaDB
            try:
                stats = triage_agent.researcher.backend.get_collection_stats()
                output = ["# Knowledge Sources\n"]

                public_sources = [
                    ("ada_standards", "ADA Standards of Care", "Evidence-based clinical guidelines"),
                    ("australian_guidelines", "Australian Diabetes Guidelines", "Technology recommendations"),
                    ("openaps_docs", "OpenAPS Documentation", "DIY closed-loop algorithms"),
                    ("loop_docs", "Loop Documentation", "iOS closed-loop system"),
                    ("androidaps_docs", "AndroidAPS Documentation", "Android closed-loop system"),
                    ("wikipedia_education", "Wikipedia T1D Education", "Educational content"),
                    ("research_papers", "PubMed Research Papers", "Peer-reviewed research"),
                ]

                output.append("## Public Knowledge Sources\n")
                for key, name, desc in public_sources:
                    count = stats.get(key, {}).get('count', 0)
                    output.append(f"- **{name}**: {desc} ({count} chunks)\n")

                # Add user sources
                user_sources = [k for k in stats.keys() if k.startswith('user_')]
                if user_sources:
                    output.append("\n## Your Product Guides\n")
                    for key in user_sources:
                        count = stats.get(key, {}).get('count', 0)
                        name = key.replace('user_', '').replace('_', ' ').title()
                        output.append(f"- **{name}** ({count} chunks)\n")

                return [TextContent(type="text", text="\n".join(output))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error loading sources: {e}")]
        
        else:
            return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]
    
    except Exception as e:
        import traceback
        error_msg = f"Error executing tool '{name}': {str(e)}\n\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        return [TextContent(type="text", text=f"Error: {str(e)}")]


def _format_search_results(results, source_name: str) -> str:
    """Format search results as readable text."""
    if not results:
        return f"No relevant information found in {source_name}."
    
    output = [f"# Search Results from {source_name}\n"]
    
    for i, result in enumerate(results, 1):
        page_info = f", Page {result.page_number}" if result.page_number else ""
        output.append(f"## Result {i} ({result.confidence:.0%} confidence{page_info})")
        output.append(f"\n{result.quote}\n")
        if result.context:
            output.append(f"*Context: {result.context}*\n")
    
    return "\n".join(output)


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
