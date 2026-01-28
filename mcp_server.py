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
                "Searches authoritative knowledge sources (Think Like a Pancreas, "
                "CamAPS FX manual, Ypsomed pump manual, FreeStyle Libre 3 manual) "
                "and returns a safe, audited answer with source citations. "
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
            name="search_theory",
            description=(
                "Search 'Think Like a Pancreas' for diabetes management theory, "
                "insulin strategies, carb counting, and behavioral guidance. "
                "Returns exact quotes with page numbers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for diabetes theory and strategies"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_camaps",
            description=(
                "Search CamAPS FX User Manual for hybrid closed-loop algorithm "
                "information, Boost/Ease-off modes, target settings, and auto-mode behavior. "
                "Returns exact quotes with page numbers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for CamAPS FX algorithm features"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_ypsomed",
            description=(
                "Search Ypsomed/mylife Pump Manual for hardware operation, "
                "cartridge changes, infusion sets, priming, and troubleshooting. "
                "Returns exact quotes with page numbers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for Ypsomed pump hardware procedures"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_libre",
            description=(
                "Search FreeStyle Libre 3 Manual for CGM sensor information, "
                "sensor application, readings, alarms, and troubleshooting. "
                "Returns exact quotes with page numbers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for Libre 3 CGM features"
                    }
                },
                "required": ["query"]
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
        
        elif name == "search_theory":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(type="text", text="Error: No query provided")]
            
            results = triage_agent.researcher.search_theory(query)
            return [TextContent(type="text", text=_format_search_results(results, "Think Like a Pancreas"))]
        
        elif name == "search_camaps":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(type="text", text="Error: No query provided")]
            
            results = triage_agent.researcher.search_camaps(query)
            return [TextContent(type="text", text=_format_search_results(results, "CamAPS FX User Manual"))]
        
        elif name == "search_ypsomed":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(type="text", text="Error: No query provided")]
            
            results = triage_agent.researcher.search_ypsomed(query)
            return [TextContent(type="text", text=_format_search_results(results, "Ypsomed Pump Manual"))]
        
        elif name == "search_libre":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(type="text", text="Error: No query provided")]
            
            results = triage_agent.researcher.search_libre(query)
            return [TextContent(type="text", text=_format_search_results(results, "FreeStyle Libre 3 Manual"))]
        
        elif name == "get_knowledge_sources":
            sources = [
                ("**Theory**", "Think Like a Pancreas", 
                 "Diabetes management concepts, insulin strategies, carb counting, blood sugar patterns"),
                ("**Algorithm**", "CamAPS FX User Manual", 
                 "Hybrid closed-loop settings, Boost/Ease modes, auto-mode behavior"),
                ("**Hardware**", "Ypsomed Pump Manual", 
                 "Pump operation, cartridge changes, infusion sets, troubleshooting"),
                ("**CGM**", "FreeStyle Libre 3 Manual", 
                 "Sensor application, readings, alarms, troubleshooting"),
            ]
            
            output = ["# Knowledge Sources\n"]
            for category, name, description in sources:
                output.append(f"{category}: **{name}**")
                output.append(f"  - {description}\n")
            
            return [TextContent(type="text", text="\n".join(output))]
        
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
