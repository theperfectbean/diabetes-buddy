"""
Diabetes Buddy Web Interface - FastAPI Application

Provides a REST API and web chat interface for Diabetes Buddy agents.
"""

import asyncio
import json
import logging
import shutil
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from agents import TriageAgent, SafetyAuditor, Severity
from agents import GlookoAnalyzer, generate_research_queries


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

# Initialize Glooko analyzer and directories
PROJECT_ROOT = Path(__file__).parent.parent
GLOOKO_DIR = PROJECT_ROOT / "data" / "glooko"
ANALYSIS_DIR = PROJECT_ROOT / "data" / "analysis"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# Ensure directories exist
GLOOKO_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Initialize Glooko analyzer
try:
    glooko_analyzer = GlookoAnalyzer(
        data_dir=str(GLOOKO_DIR),
        cache_dir=str(CACHE_DIR)
    )
    logger.info("Glooko analyzer initialized successfully")
except Exception as e:
    logger.warning(f"Glooko analyzer initialization failed (non-fatal): {e}")
    glooko_analyzer = None

# Maximum upload size (50MB)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


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


class GlookoUploadResponse(BaseModel):
    """Response model for Glooko file upload."""
    success: bool
    message: str
    filename: str
    file_path: str
    records_found: dict


class GlookoAnalysisResponse(BaseModel):
    """Response model for Glooko analysis."""
    success: bool
    analysis_date: str
    file_analyzed: str
    metrics: dict
    patterns: list[dict]
    research_queries: list[dict]
    warnings: list[str]


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
            "safety": safety_auditor is not None,
            "glooko": glooko_analyzer is not None
        }
    }


# ============================================
# Glooko Data Analysis Endpoints
# ============================================

@app.post("/api/upload-glooko", responses={
    200: {"description": "File uploaded successfully"},
    400: {"description": "Invalid file (not a ZIP or too large)"},
    429: {"description": "Rate limit exceeded"},
    500: {"description": "Internal server error"}
})
async def upload_glooko(request: Request, file: UploadFile = File(...)):
    """
    Upload a Glooko export ZIP file.

    - Accepts ZIP files up to 50MB
    - Validates ZIP structure contains expected CSV files
    - Stores file in data/glooko/ directory
    - Returns count of records found in each data type
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only ZIP files are accepted")

    # Read file and check size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB"
        )

    # Validate ZIP structure
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(content), 'r') as zf:
            file_list = zf.namelist()
            # Check for expected Glooko CSV files
            csv_files = [f for f in file_list if f.lower().endswith('.csv')]
            if not csv_files:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP file does not contain any CSV files"
                )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"glooko_export_{timestamp}.zip"
    file_path = GLOOKO_DIR / safe_filename

    # Save file
    try:
        with open(file_path, 'wb') as f:
            f.write(content)
        logger.info(f"Saved Glooko export: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # Quick parse to count records
    records_found = {"csv_files": len(csv_files)}
    if glooko_analyzer:
        try:
            data = glooko_analyzer.parser.parse_export(str(file_path))
            records_found = {
                "glucose_readings": len(data.glucose),
                "insulin_records": len(data.insulin),
                "carb_entries": len(data.carbs),
                "activity_logs": len(data.activity),
                "notes": len(data.notes),
            }
        except Exception as e:
            logger.warning(f"Could not parse file for record counts: {e}")

    return GlookoUploadResponse(
        success=True,
        message="File uploaded successfully",
        filename=safe_filename,
        file_path=str(file_path),
        records_found=records_found
    )


@app.get("/api/glooko-analysis/latest", responses={
    200: {"description": "Latest analysis results"},
    404: {"description": "No analysis available"},
    500: {"description": "Internal server error"}
})
async def get_latest_analysis():
    """
    Get the most recent Glooko analysis results.

    Returns cached analysis if available, otherwise runs new analysis
    on the most recently uploaded file.
    """
    if not glooko_analyzer:
        raise HTTPException(status_code=500, detail="Glooko analyzer not available")

    # Check for cached analysis
    analysis_files = sorted(ANALYSIS_DIR.glob("analysis_*.json"), reverse=True)
    if analysis_files:
        try:
            with open(analysis_files[0], 'r') as f:
                cached = json.load(f)
                return JSONResponse(content=cached)
        except Exception as e:
            logger.warning(f"Could not load cached analysis: {e}")

    # Find most recent Glooko file
    glooko_files = sorted(GLOOKO_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not glooko_files:
        raise HTTPException(status_code=404, detail="No Glooko exports found. Please upload a file first.")

    # Run analysis
    try:
        return await run_glooko_analysis_internal(str(glooko_files[0]))
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/api/glooko-analysis/history", responses={
    200: {"description": "List of available analyses"},
    500: {"description": "Internal server error"}
})
async def get_analysis_history():
    """
    Get list of all available Glooko analyses.

    Returns metadata about each saved analysis for browsing history.
    """
    history = []

    # Get all analysis files
    analysis_files = sorted(ANALYSIS_DIR.glob("analysis_*.json"), reverse=True)

    for analysis_file in analysis_files[:20]:  # Limit to last 20
        try:
            with open(analysis_file, 'r') as f:
                data = json.load(f)
                history.append({
                    "id": analysis_file.stem,
                    "date": data.get("analysis_date", "unknown"),
                    "file": data.get("file_analyzed", "unknown"),
                    "time_in_range": data.get("metrics", {}).get("time_in_range_percent"),
                    "patterns_found": len(data.get("patterns", [])),
                })
        except Exception as e:
            logger.warning(f"Could not read analysis file {analysis_file}: {e}")
            continue

    # Also list uploaded files without analysis
    glooko_files = list(GLOOKO_DIR.glob("*.zip"))
    analyzed_files = {h["file"] for h in history}

    for gf in glooko_files:
        if gf.name not in analyzed_files:
            history.append({
                "id": None,
                "date": None,
                "file": gf.name,
                "time_in_range": None,
                "patterns_found": None,
                "status": "not_analyzed"
            })

    return {"history": history, "total": len(history)}


@app.post("/api/glooko-analysis/run", responses={
    200: {"description": "Analysis completed successfully"},
    400: {"description": "Invalid file specified"},
    500: {"description": "Analysis failed"}
})
async def run_analysis(request: Request, filename: Optional[str] = None):
    """
    Run Glooko analysis on a specific file or the most recent upload.

    - If filename provided, analyzes that specific file
    - Otherwise analyzes the most recently uploaded file
    - Saves results to data/analysis/ for future retrieval
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if not glooko_analyzer:
        raise HTTPException(status_code=500, detail="Glooko analyzer not available")

    # Determine which file to analyze
    if filename:
        file_path = GLOOKO_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {filename}")
    else:
        glooko_files = sorted(GLOOKO_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not glooko_files:
            raise HTTPException(status_code=400, detail="No Glooko exports found")
        file_path = glooko_files[0]

    try:
        return await run_glooko_analysis_internal(str(file_path))
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def run_glooko_analysis_internal(file_path: str) -> JSONResponse:
    """Internal function to run Glooko analysis and save results."""
    file_name = Path(file_path).name

    # Run analysis
    logger.info(f"Running analysis on: {file_path}")
    result = glooko_analyzer.analyze(file_path)

    # Generate research queries
    queries = generate_research_queries(result)

    # Build response
    response_data = {
        "success": True,
        "analysis_date": datetime.now().isoformat(),
        "file_analyzed": file_name,
        "metrics": {
            "total_glucose_readings": result.metrics.total_readings,
            "date_range_days": result.metrics.date_range_days,
            "average_glucose": round(result.metrics.average_glucose, 1) if result.metrics.average_glucose else None,
            "std_deviation": round(result.metrics.std_deviation, 1) if result.metrics.std_deviation else None,
            "coefficient_of_variation": round(result.metrics.coefficient_of_variation, 1) if result.metrics.coefficient_of_variation else None,
            "time_in_range_percent": round(result.metrics.time_in_range_percent, 1) if result.metrics.time_in_range_percent else None,
            "time_below_range_percent": round(result.metrics.time_below_range_percent, 1) if result.metrics.time_below_range_percent else None,
            "time_above_range_percent": round(result.metrics.time_above_range_percent, 1) if result.metrics.time_above_range_percent else None,
            "average_daily_carbs": round(result.metrics.average_daily_carbs, 1) if result.metrics.average_daily_carbs else None,
            "average_daily_insulin": round(result.metrics.average_daily_insulin, 1) if result.metrics.average_daily_insulin else None,
        },
        "patterns": [
            {
                "type": p.pattern_type.value,
                "description": p.description,
                "confidence": round(p.confidence, 2),
                "affected_readings": p.affected_readings,
                "recommendation": p.recommendation,
            }
            for p in result.patterns
        ],
        "research_queries": [
            {
                "query": q["query"],
                "pattern_type": q["pattern_type"],
                "priority": q["priority"],
            }
            for q in queries
        ],
        "warnings": result.warnings,
    }

    # Save analysis results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    analysis_file = ANALYSIS_DIR / f"analysis_{timestamp}.json"
    try:
        with open(analysis_file, 'w') as f:
            json.dump(response_data, f, indent=2)
        logger.info(f"Saved analysis to: {analysis_file}")
    except Exception as e:
        logger.warning(f"Could not save analysis: {e}")

    return JSONResponse(content=response_data)


@app.get("/api/glooko-analysis/{analysis_id}", responses={
    200: {"description": "Analysis results"},
    404: {"description": "Analysis not found"}
})
async def get_analysis_by_id(analysis_id: str):
    """Get a specific analysis by ID."""
    analysis_file = ANALYSIS_DIR / f"{analysis_id}.json"
    if not analysis_file.exists():
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        with open(analysis_file, 'r') as f:
            return JSONResponse(content=json.load(f))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load analysis: {e}")


# Mount static files
web_dir = Path(__file__).parent
static_dir = web_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
