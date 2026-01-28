"""
Diabetes Buddy Web Interface - FastAPI Application

Provides a REST API and web chat interface for Diabetes Buddy agents.
"""

import asyncio
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from agents import TriageAgent, SafetyAuditor, Severity


# Rate limiter implementation
class RateLimiter:
    """In-memory rate limiter for API requests."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests: dict[str, list[datetime]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> bool:
        async with self._lock:
            now = datetime.now()
            cutoff = now - self.window
            # Clean old requests
            self.requests[client_ip] = [
                t for t in self.requests[client_ip] if t > cutoff
            ]
            if len(self.requests[client_ip]) >= self.max_requests:
                return False
            self.requests[client_ip].append(now)
            return True


# Initialize rate limiter
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

# Initialize FastAPI app
app = FastAPI(
    title="Diabetes Buddy API",
    description="""
AI-powered diabetes management assistant.

## Features
- Natural language query processing
- Multi-source knowledge retrieval (Think Like a Pancreas, CamAPS FX, Ypsomed, Libre 3)
- Safety auditing with dose detection
- Severity-based response classification

## Rate Limits
- 10 requests per minute per IP address
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Initialize agents
try:
    logger.info("Initializing Diabetes Buddy agents...")
    triage_agent = TriageAgent()
    safety_auditor = SafetyAuditor()
    logger.info("Agents initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize agents: {e}")
    sys.exit(1)


# Request/Response models
class QueryRequest(BaseModel):
    """Request model for diabetes queries."""
    query: str = Field(..., min_length=1, max_length=2000, description="The diabetes-related question to ask")

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        if len(v) < 3:
            raise ValueError("Query too short - please ask a complete question")
        return v


class QueryResponse(BaseModel):
    """Response model for diabetes queries."""
    query: str
    classification: str
    confidence: float
    severity: str
    answer: str
    sources: list[dict]
    disclaimer: str


# Routes
@app.get("/")
async def index():
    """Serve the web interface."""
    web_dir = Path(__file__).parent
    return FileResponse(web_dir / "index.html")


@app.post("/api/query", responses={
    200: {"description": "Successful query response"},
    400: {"description": "Invalid query (empty, too short, or too long)"},
    429: {"description": "Rate limit exceeded"},
    500: {"description": "Internal server error"}
})
async def query(request: Request, query_request: QueryRequest) -> QueryResponse:
    """
    Process a diabetes management query.

    - Classifies the query to determine relevant knowledge sources
    - Searches across diabetes management manuals and guides
    - Applies safety auditing to detect dangerous content
    - Returns sourced answer with severity classification
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a moment before trying again."
        )

    try:
        logger.info(f"Processing query: {query_request.query[:50]}...")

        # Process through triage agent
        triage_response = triage_agent.process(query_request.query)

        # Check safety
        safety_result = safety_auditor.audit_text(
            text=triage_response.synthesized_answer,
            query=query_request.query
        )

        # Prepare sources (increased to 3 per source with longer excerpts)
        sources = []
        for source_name, results in triage_response.results.items():
            for result in results[:3]:  # Top 3 per source
                sources.append({
                    "source": result.source,
                    "page": result.page_number,
                    "excerpt": result.quote[:300] + "..." if len(result.quote) > 300 else result.quote,
                    "confidence": result.confidence,
                    "full_excerpt": result.quote  # Include full text for detailed view
                })

        logger.info(f"Query processed successfully. Severity: {safety_result.max_severity.name}")

        # Build response
        return QueryResponse(
            query=query_request.query,
            classification=triage_response.classification.category.value,
            confidence=triage_response.classification.confidence,
            severity=safety_result.max_severity.name,
            answer=safety_result.safe_response,
            sources=sources,
            disclaimer="This is educational information only. Always consult your healthcare provider before making changes to your diabetes management routine."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while processing your question. Please try again.")


@app.get("/api/sources")
async def get_sources():
    """Get list of available knowledge sources."""
    return {
        "sources": [
            {
                "name": "Think Like a Pancreas",
                "author": "Gary Scheiner",
                "type": "theory",
                "description": "Diabetes management concepts and strategies"
            },
            {
                "name": "CamAPS FX User Manual",
                "type": "camaps",
                "description": "Closed-loop algorithm settings and modes"
            },
            {
                "name": "Ypsomed Pump Manual",
                "type": "ypsomed",
                "description": "Pump hardware and operation"
            },
            {
                "name": "FreeStyle Libre 3 Manual",
                "type": "libre",
                "description": "CGM sensor and glucose readings"
            }
        ]
    }


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Diabetes Buddy Web API",
        "version": "1.0.0",
        "agents": {
            "triage": triage_agent is not None,
            "safety": safety_auditor is not None
        }
    }


# Mount static files
web_dir = Path(__file__).parent
static_dir = web_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
