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

from agents import TriageAgent, SafetyAuditor, Severity, QueryCategory
from agents import GlookoAnalyzer, GlookoQueryAgent, generate_research_queries
from agents.glucose_units import GLUCOSE_UNIT, convert_to_configured_unit


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
- Multi-source knowledge retrieval (Think Like a Pancreas, CamAPS FX, Ypsomed, Libre 3, ADA Standards 2026, Australian Guidelines)
- Clinical guideline citations for evidence-based recommendations
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
    glooko_query_agent = GlookoQueryAgent()
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
    glooko_analyzer = GlookoAnalyzer(use_cache=True)
    logger.info("Glooko analyzer initialized successfully")
except Exception as e:
    logger.error(f"Glooko analyzer initialization failed: {e}", exc_info=True)
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
    - Routes to GlookoQueryAgent for personal data queries
    - Searches across diabetes management manuals and guides for knowledge queries
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

        # Handle glooko_data queries separately
        if triage_response.classification.category == QueryCategory.GLOOKO_DATA:
            logger.info("Query classified as glooko_data - routing to GlookoQueryAgent")
            query_result = glooko_query_agent.process_query(query_request.query)
            
            if not query_result.success:
                answer = query_result.answer
            else:
                answer = query_result.answer
            
            # Apply safety auditing
            safety_result = safety_auditor.audit_text(
                text=answer,
                query=query_request.query
            )
            
            # Build sources list for data queries
            sources = []
            if query_result.date_range_start:
                sources.append({
                    "source": "Your Glooko Data",
                    "page": None,
                    "excerpt": f"Analysis period: {query_result.date_range_start} to {query_result.date_range_end}",
                    "confidence": 1.0,
                    "full_excerpt": f"Data points used: {query_result.data_points_used}\n{query_result.context}"
                })
            
            return QueryResponse(
                query=query_request.query,
                classification=triage_response.classification.category.value,
                confidence=triage_response.classification.confidence,
                severity=safety_result.max_severity.name,
                answer=safety_result.safe_response,
                sources=sources,
                disclaimer="This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team."
            )

        # Handle knowledge-based queries (theory, camaps, ypsomed, libre, hybrid)
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
                "name": "Your Glooko Data",
                "type": "glooko_data",
                "description": "Your personal diabetes data from Glooko exports"
            },
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
            },
            {
                "name": "ADA Standards of Care 2026",
                "type": "clinical_guidelines",
                "description": "Evidence-based treatment targets, glycemic goals, and complication management"
            },
            {
                "name": "Australian Diabetes Guidelines",
                "type": "clinical_guidelines",
                "description": "Technology recommendations for CGM, pumps, and hybrid closed-loop systems"
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
            "glooko_query": glooko_query_agent is not None,
            "glooko_analyzer": glooko_analyzer is not None
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
    result = glooko_analyzer.process_export(file_path)

    # Generate research queries from the full result
    queries = generate_research_queries(result)

    # Extract metrics from time_in_range data
    tir_data = result.get("time_in_range", {})
    analysis_period = result.get("analysis_period", {})
    patterns_dict = result.get("patterns", {})
    
    # Convert patterns dict to list format for frontend
    patterns_list = []
    for pattern_type, pattern_data in patterns_dict.items():
        if isinstance(pattern_data, dict) and pattern_data.get("detected"):
            patterns_list.append({
                "type": pattern_type,
                "description": pattern_data.get("description", "Pattern detected"),
                "confidence": round(pattern_data.get("confidence", 50), 2),
                "affected_readings": pattern_data.get("affected_readings", 0),
                "recommendation": pattern_data.get("recommendation", "Discuss with your healthcare team"),
            })
    
    # Build response
    # Convert glucose values to configured unit
    avg_glucose_mgdl = tir_data.get("average_glucose")
    avg_glucose_configured = convert_to_configured_unit(avg_glucose_mgdl) if avg_glucose_mgdl else None
    std_mgdl = tir_data.get("glucose_std")
    std_configured = convert_to_configured_unit(std_mgdl) if std_mgdl else None
    
    response_data = {
        "success": True,
        "analysis_date": datetime.now().isoformat(),
        "file_analyzed": file_name,
        "metrics": {
            "total_glucose_readings": tir_data.get("total_readings", 0),
            "date_range_days": analysis_period.get("days", 0),
            "average_glucose": avg_glucose_configured,
            "glucose_unit": GLUCOSE_UNIT,
            "std_deviation": std_configured,
            "coefficient_of_variation": round(tir_data.get("coefficient_of_variation", 0), 1),
            "time_in_range_percent": round(tir_data.get("time_in_range_70_180", 0), 1),
            "time_below_range_percent": round(tir_data.get("time_below_70", 0), 1),
            "time_above_range_percent": round(tir_data.get("time_above_180", 0), 1),
            "average_daily_carbs": None,  # Not available in current structure
            "average_daily_insulin": None,  # Not available in current structure
        },
        "patterns": patterns_list,
        "research_queries": [
            {
                "query": q.get("question", q.get("query", "")),
                "pattern_type": q["pattern_type"],
                "priority": q["priority"],
            }
            for q in queries
        ],
        "warnings": result.get("anomalies", []),
        "recommendations": result.get("recommendations", []),
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


# ============================================================================
# Knowledge Base Management Endpoints
# ============================================================================

from agents.knowledge_fetcher import KnowledgeFetcher

# Initialize knowledge fetcher
knowledge_fetcher = KnowledgeFetcher()


class DeviceSetupRequest(BaseModel):
    """Request model for device setup."""
    pump_id: str = Field(..., description="Pump device ID from registry")
    cgm_id: str = Field(..., description="CGM device ID from registry")


@app.get("/api/knowledge/registry")
async def get_device_registry():
    """Get the complete device registry for setup UI."""
    try:
        registry_path = Path(__file__).parent.parent / "config" / "device_registry.json"
        with open(registry_path, 'r') as f:
            registry = json.load(f)
        
        # Format for UI display
        return {
            "pumps": {
                key: {
                    "id": key,
                    "name": info["name"],
                    "manufacturer": info["manufacturer"]
                }
                for key, info in registry.get("insulin_pumps", {}).items()
            },
            "cgms": {
                key: {
                    "id": key,
                    "name": info["name"],
                    "manufacturer": info["manufacturer"]
                }
                for key, info in registry.get("cgm_devices", {}).items()
            }
        }
    except Exception as e:
        logger.error(f"Error loading device registry: {e}")
        raise HTTPException(status_code=500, detail="Failed to load device registry")


@app.post("/api/knowledge/setup")
async def setup_knowledge_base(setup_request: DeviceSetupRequest):
    """
    Initial setup: Select devices and fetch all knowledge sources.
    This is the primary onboarding endpoint.
    """
    try:
        logger.info(f"Starting knowledge base setup: {setup_request.pump_id} + {setup_request.cgm_id}")
        
        # Run setup (this fetches all sources)
        results = knowledge_fetcher.setup_user_devices(
            pump_id=setup_request.pump_id,
            cgm_id=setup_request.cgm_id
        )
        
        # Count successes and failures
        successes = sum(1 for r in results.values() if r.get('success'))
        failures = sum(1 for r in results.values() if not r.get('success'))
        
        return {
            "success": failures == 0,
            "message": f"Knowledge base setup completed. {successes} sources fetched successfully.",
            "results": results,
            "profile": knowledge_fetcher.get_user_profile()
        }
        
    except Exception as e:
        logger.error(f"Knowledge base setup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Setup failed: {str(e)}")


@app.get("/api/knowledge/status")
async def get_knowledge_status():
    """Get status of all configured knowledge sources."""
    try:
        statuses = knowledge_fetcher.get_all_sources_status()
        profile = knowledge_fetcher.get_user_profile()
        
        return {
            "sources": statuses,
            "profile": profile,
            "last_check": profile.get("last_update_check"),
            "auto_update_enabled": profile.get("auto_update_enabled", True)
        }
    except Exception as e:
        logger.error(f"Error getting knowledge status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get knowledge status")


@app.post("/api/knowledge/check-updates")
async def check_for_updates():
    """Manually trigger update check for all sources."""
    try:
        logger.info("Manual update check triggered")
        updates = knowledge_fetcher.check_for_updates()
        
        # Count updates found
        updates_available = sum(1 for r in updates.values() if r.get('update_available'))
        
        return {
            "success": True,
            "updates_found": updates_available,
            "details": updates
        }
    except Exception as e:
        logger.error(f"Update check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Update check failed: {str(e)}")


class DeviceUpdateRequest(BaseModel):
    """Request model for changing devices."""
    device_type: str = Field(..., description="'pump' or 'cgm'")
    device_id: str = Field(..., description="New device ID from registry")


@app.post("/api/knowledge/update-device")
async def update_device(update_request: DeviceUpdateRequest):
    """Change pump or CGM and fetch new manual."""
    try:
        result = knowledge_fetcher.update_device(
            device_type=update_request.device_type,
            device_id=update_request.device_id
        )
        
        return {
            "success": result.get('success', False),
            "message": f"Device updated to {update_request.device_id}",
            "result": result
        }
    except Exception as e:
        logger.error(f"Device update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Device update failed: {str(e)}")


@app.get("/api/knowledge/notifications")
async def get_notifications():
    """Get recent update notifications."""
    try:
        notifications_file = Path(__file__).parent.parent / "data" / "notifications.json"
        if not notifications_file.exists():
            return {"notifications": []}
        
        with open(notifications_file, 'r') as f:
            notifications = json.load(f)
        
        # Return only unread or recent (last 30 days)
        cutoff = datetime.now() - timedelta(days=30)
        recent = [
            n for n in notifications
            if not n.get('read') or datetime.fromisoformat(n['timestamp']) > cutoff
        ]
        
        return {"notifications": recent}
    except Exception as e:
        logger.error(f"Error loading notifications: {e}")
        return {"notifications": []}


# Mount static files
web_dir = Path(__file__).parent
static_dir = web_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/setup")
async def setup_page():
    """Serve the knowledge base setup page."""
    setup_html = web_dir / "setup.html"
    if setup_html.exists():
        return FileResponse(setup_html)
    raise HTTPException(status_code=404, detail="Setup page not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
