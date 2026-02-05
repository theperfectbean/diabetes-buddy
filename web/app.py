"""
Diabetes Buddy Web Interface - FastAPI Application

Provides a REST API and web chat interface for Diabetes Buddy agents.
"""

import asyncio
import json
import logging
import logging.handlers
import shutil
import sys
import yaml
import zipfile
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Load configuration
try:
    with open(Path(__file__).parent.parent / "config" / "hybrid_knowledge.yaml", 'r') as f:
        config = yaml.safe_load(f)
except Exception as e:
    print(f"Warning: Could not load config file: {e}")
    config = {}

# Configure logging with rotation
log_config = config.get('logging', {})
log_level = getattr(logging, log_config.get('level', 'INFO').upper())
log_file = log_config.get('file_path', 'logs/hybrid_system.log')
max_size_mb = log_config.get('max_size_mb', 10)
backup_count = log_config.get('backup_count', 5)

# Ensure logs directory exists
Path(log_file).parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,  # Convert MB to bytes
            backupCount=backup_count
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from agents import TriageAgent, SafetyAuditor, Severity, QueryCategory
from agents import GlookoAnalyzer, GlookoQueryAgent, generate_research_queries
from agents import UnifiedAgent
from agents.glucose_units import GLUCOSE_UNIT, convert_to_configured_unit
from agents.source_manager import UserSourceManager
from agents.analytics import ExperimentAnalytics
from agents.device_detection import UserDeviceManager


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""

    # Startup
    logger.info("Starting Diabetes Buddy API...")

    yield

    # Shutdown
    logger.info("Shutting down Diabetes Buddy API...")
    logger.info("Shutdown complete")


# Initialize FastAPI app
app = FastAPI(
    title="Diabetes Buddy API",
    lifespan=lifespan,
    description="""
AI-powered diabetes management assistant.

## Features
- Natural language query processing
- Multi-source knowledge retrieval (Public medical guidelines + User-uploaded device manuals)
- Clinical guideline citations for evidence-based recommendations
- Safety auditing with dose detection
- Severity-based response classification
- Product-agnostic device support via PDF upload

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
    unified_agent = UnifiedAgent()
    
    # Initialize safety auditor with LLM provider for flexible intent classification
    llm_provider = unified_agent.llm if hasattr(unified_agent, 'llm') else None
    safety_auditor = SafetyAuditor(llm_provider=llm_provider)
    logger.info(f"Safety auditor initialized {'with' if llm_provider else 'without'} LLM-based intent classification")
    
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
CONVERSATIONS_DIR = PROJECT_ROOT / "data" / "conversations"

# Ensure directories exist
GLOOKO_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize Glooko analyzer
try:
    glooko_analyzer = GlookoAnalyzer(use_cache=True)
    logger.info("Glooko analyzer initialized successfully")
except Exception as e:
    logger.error(f"Glooko analyzer initialization failed: {e}", exc_info=True)
    glooko_analyzer = None

# Maximum upload size (50MB)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


class ConversationSummary(BaseModel):
    """Summary of a conversation for the sidebar."""
    id: str
    timestamp: str
    firstQuery: str
    messageCount: int


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    type: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    data: Optional[dict] = None  # For assistant messages with additional data


class ConversationData(BaseModel):
    """Full conversation data."""
    id: str
    messages: list[ConversationMessage]
    created: str
    updated: str


class ConversationManager:
    """Manages conversation storage and retrieval."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir

    def _get_conversation_path(self, conversation_id: str) -> Path:
        """Get the file path for a conversation."""
        return self.storage_dir / f"{conversation_id}.json"

    def create_conversation(self) -> str:
        """Create a new conversation and return its ID."""
        conversation_id = f"conv_{int(datetime.now().timestamp() * 1000)}_{''.join(str(ord(c) % 10) for c in str(datetime.now())[-6:])}"
        conversation_data = ConversationData(
            id=conversation_id,
            messages=[],
            created=datetime.now().isoformat(),
            updated=datetime.now().isoformat()
        )
        self._save_conversation(conversation_data)
        return conversation_id

    def save_message(self, conversation_id: str, message: "ConversationMessage"):
        """Save a message to a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            # Create conversation if it doesn't exist
            conversation = ConversationData(
                id=conversation_id,
                messages=[],
                created=datetime.now().isoformat(),
                updated=datetime.now().isoformat()
            )

        conversation.messages.append(message)
        conversation.updated = datetime.now().isoformat()
        self._save_conversation(conversation)

    def get_conversation(self, conversation_id: str) -> Optional["ConversationData"]:
        """Get a full conversation by ID."""
        path = self._get_conversation_path(conversation_id)
        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ConversationData(**data)
        except Exception as e:
            logger.error(f"Failed to load conversation {conversation_id}: {e}")
            return None

    def get_conversation_summaries(self) -> List[ConversationSummary]:
        """Get summaries of all conversations, sorted by most recent."""
        summaries = []
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                conversation = ConversationData(**data)
                if conversation.messages:  # Only include conversations with messages
                    first_query = ""
                    for msg in conversation.messages:
                        if msg.type == "user":
                            first_query = msg.content[:40] + ("..." if len(msg.content) > 40 else "")
                            break

                    summary = ConversationSummary(
                        id=conversation.id,
                        timestamp=conversation.updated,
                        firstQuery=first_query,
                        messageCount=len(conversation.messages)
                    )
                    summaries.append(summary)
            except Exception as e:
                logger.error(f"Failed to load conversation summary for {path}: {e}")

        # Sort by timestamp, most recent first
        summaries.sort(key=lambda x: x.timestamp, reverse=True)
        return summaries

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        path = self._get_conversation_path(conversation_id)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception as e:
                logger.error(f"Failed to delete conversation {conversation_id}: {e}")
        return False

    def _save_conversation(self, conversation: "ConversationData"):
        """Save conversation data to file."""
        path = self._get_conversation_path(conversation.id)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(conversation.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save conversation {conversation.id}: {e}")


# Initialize conversation manager
conversation_manager = ConversationManager(CONVERSATIONS_DIR)


# Request/Response models
class QueryRequest(BaseModel):
    """Request model for diabetes queries."""
    query: str = Field(..., min_length=1, max_length=2000, description="The diabetes-related question to ask")
    conversation_id: Optional[str] = Field(None, description="The conversation ID to save messages to")

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
    # Knowledge source transparency fields
    knowledge_breakdown: Optional[dict] = None
    primary_source_type: str = "unknown"


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


class SourceUploadResponse(BaseModel):
    """Response model for source upload."""
    success: bool
    filename: str
    display_name: str
    collection_key: str
    message: str
    device_profile_complete: Optional[bool] = None
    device_profile: Optional[dict] = None


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
                disclaimer=safety_result.tier_disclaimer or "This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team."
            )

        # Handle knowledge-based queries (theory, camaps, ypsomed, libre, hybrid)
        # DEBUG: Log the response before safety check
        logger.info(f"[DEBUG] Response before safety check (FULL): {triage_response.synthesized_answer}")
        
        # Check safety
        safety_result = safety_auditor.audit_text(
            text=triage_response.synthesized_answer,
            query=query_request.query
        )
        
        # DEBUG: Log safety decision
        logger.info(f"[DEBUG] Safety tier: {safety_result.tier}, action: {safety_result.tier_action}, reason: {safety_result.tier_reason}")

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

        # Save messages to conversation if conversation_id provided
        if query_request.conversation_id:
            try:
                # Save user message
                user_message = ConversationMessage(
                    type="user",
                    content=query_request.query,
                    timestamp=datetime.now().isoformat()
                )
                conversation_manager.save_message(query_request.conversation_id, user_message)

                # Save assistant message
                assistant_message = ConversationMessage(
                    type="assistant",
                    content=safety_result.safe_response,
                    timestamp=datetime.now().isoformat(),
                    data={
                        "classification": triage_response.classification.category.value,
                        "confidence": triage_response.classification.confidence,
                        "severity": safety_result.max_severity.name,
                        "sources": sources,
                        "disclaimer": safety_result.tier_disclaimer or "This is educational information only. Always consult your healthcare provider before making changes to your diabetes management routine."
                    }
                )
                conversation_manager.save_message(query_request.conversation_id, assistant_message)
            except Exception as e:
                logger.error(f"Failed to save conversation messages: {e}")

        # Build response
        return QueryResponse(
            query=query_request.query,
            classification=triage_response.classification.category.value,
            confidence=triage_response.classification.confidence,
            severity=safety_result.max_severity.name,
            answer=safety_result.safe_response,
            sources=sources,
            disclaimer=safety_result.tier_disclaimer or "This is educational information only. Always consult your healthcare provider before making changes to your diabetes management routine."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while processing your question. Please try again.")


@app.post("/api/query/unified", responses={
    200: {"description": "Successful query response"},
    429: {"description": "Rate limit exceeded"},
    500: {"description": "Internal server error"}
})
async def query_unified(request: Request, query_request: QueryRequest) -> QueryResponse:
    """
    Process a query using the unified agent (no routing).

    Every query gets both user's Glooko data and knowledge base results.
    The LLM decides what's relevant - no classification step.
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        logger.info(f"Processing unified query: {query_request.query[:50]}...")

        # Process through unified agent
        response = unified_agent.process(query_request.query)

        if not response.success:
            raise HTTPException(status_code=500, detail=response.answer)

        # Apply safety auditing
        # Use hybrid audit for parametric responses, standard audit for RAG-only
        if response.requires_enhanced_safety_check or 'parametric' in response.sources_used:
            # Use hybrid audit for parametric responses
            safety_result = safety_auditor.audit_hybrid_response(
                response={
                    'answer': response.answer,
                    'sources_used': response.sources_used,
                    'requires_enhanced_safety_check': response.requires_enhanced_safety_check,
                    'rag_quality': response.rag_quality.__dict__ if response.rag_quality else None,
                },
                query=query_request.query
            )
            # Log hybrid safety check results
            if hasattr(safety_result, 'hybrid_safety_checks_passed'):
                logger.info(f"Hybrid safety checks passed: {safety_result.hybrid_safety_checks_passed}, "
                           f"parametric_ratio: {safety_result.parametric_ratio:.1%}")
        else:
            # Standard audit for RAG-only responses
            safety_result = safety_auditor.audit_text(
                text=response.answer,
                query=query_request.query
            )

        # Build sources list based on what was used
        sources = []
        if "glooko" in response.sources_used:
            sources.append({
                "source": "Your Glooko Data",
                "page": None,
                "excerpt": "Personal diabetes data from your uploaded export",
                "confidence": 1.0
            })
        if "rag" in response.sources_used:
            # Include RAG quality info if available
            rag_info = ""
            if response.rag_quality:
                rag_info = f" ({response.rag_quality.chunk_count} chunks, {response.rag_quality.topic_coverage} coverage)"
            sources.append({
                "source": "Knowledge Base (RAG)",
                "page": None,
                "excerpt": f"Information from diabetes management guides and clinical guidelines{rag_info}",
                "confidence": response.rag_quality.avg_confidence if response.rag_quality else 0.9
            })
        if "parametric" in response.sources_used:
            sources.append({
                "source": "General Medical Knowledge",
                "page": None,
                "excerpt": "Supplemental information from general medical/physiological knowledge",
                "confidence": 0.6
            })
        # Backward compatibility: handle old "knowledge_base" source type
        if "knowledge_base" in response.sources_used and "rag" not in response.sources_used:
            sources.append({
                "source": "Knowledge Base",
                "page": None,
                "excerpt": "Information from diabetes management guides and clinical guidelines",
                "confidence": 0.9
            })

        # Save messages to conversation if conversation_id provided
        if query_request.conversation_id:
            try:
                # Save user message
                user_message = ConversationMessage(
                    type="user",
                    content=query_request.query,
                    timestamp=datetime.now().isoformat()
                )
                conversation_manager.save_message(query_request.conversation_id, user_message)

                # Save assistant message
                assistant_message = ConversationMessage(
                    type="assistant",
                    content=safety_result.safe_response,
                    timestamp=datetime.now().isoformat(),
                    data={
                        "classification": "unified",
                        "confidence": 1.0,
                        "severity": safety_result.max_severity.name,
                        "sources": sources,
                        "disclaimer": safety_result.tier_disclaimer or response.disclaimer or "Always consult your healthcare provider."
                    }
                )
                conversation_manager.save_message(query_request.conversation_id, assistant_message)
            except Exception as e:
                logger.error(f"Failed to save conversation messages: {e}")

        # Extract knowledge breakdown for response
        kb = response.knowledge_breakdown
        knowledge_breakdown_dict = kb.__dict__ if kb else None
        primary_type = kb.primary_source_type if kb else "unknown"
        blended_confidence = kb.blended_confidence if kb else 1.0

        return QueryResponse(
            query=query_request.query,
            classification="unified",  # No classification needed
            confidence=blended_confidence,
            severity=safety_result.max_severity.name,
            answer=safety_result.safe_response,
            sources=sources,
            disclaimer=safety_result.tier_disclaimer or response.disclaimer or "Always consult your healthcare provider.",
            knowledge_breakdown=knowledge_breakdown_dict,
            primary_source_type=primary_type
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in unified query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred processing your question.")


@app.get("/api/query/stream", responses={
    200: {"description": "Successful streaming query response"},
    429: {"description": "Rate limit exceeded"},
    500: {"description": "Internal server error"}
})
async def query_stream(request: Request, query: str, conversation_id: Optional[str] = None):
    """
    Process a query with streaming response using Server-Sent Events.

    Returns a stream of text chunks as they're generated by the LLM.

    - Uses unified agent for comprehensive knowledge retrieval
    - Streams response word-by-word for smooth user experience
    - Includes safety checks for dangerous queries
    - Saves messages to conversation if conversation_id provided
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        logger.info(f"Processing streaming query: {query[:50]}...")

        # Validate query
        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        if len(query.strip()) < 3:
            raise HTTPException(status_code=400, detail="Query too short - please ask a complete question")
        query = query.strip()

        # Save user message to conversation if conversation_id provided
        if conversation_id:
            try:
                user_message = ConversationMessage(
                    type="user",
                    content=query,
                    timestamp=datetime.now().isoformat()
                )
                conversation_manager.save_message(conversation_id, user_message)
            except Exception as e:
                logger.error(f"Failed to save user message: {e}")

        # Set up Server-Sent Events response
        async def generate():
            full_response = []  # Accumulate chunks for saving
            try:
                import asyncio
                import time

                start_time = time.time()

                logger.info(f"[DEBUG] Calling unified_agent.process() for query: {query[:50]}")
                response = unified_agent.process(query, session_id=conversation_id)
                logger.info(f"[API] Got response from unified_agent, answer length: {len(response.answer if response.answer else '')}, success: {response.success}")
                if not response.success:
                    logger.warning(f"[API] Response marked as failure: {response.answer[:100]}")
                response_dict = {
                    "answer": response.answer,
                    "sources_used": response.sources_used,
                    "requires_enhanced_safety_check": response.requires_enhanced_safety_check,
                    "rag_quality": response.rag_quality.__dict__ if response.rag_quality else {},
                }
                logger.info(f"[API] Calling safety_auditor.audit_hybrid_response() on answer of {len(response.answer)} chars")
                safety_result = safety_auditor.audit_hybrid_response(
                    response_dict,
                    query=query,
                    add_guideline_citations=False,
                )

                safe_text = safety_result.safe_response
                logger.info(f"[API] After safety audit: {len(safe_text if safe_text else '')} chars, tier: {safety_result.tier}, action: {safety_result.tier_action}")

                chunk_size = 160
                for i in range(0, len(safe_text), chunk_size):
                    chunk = safe_text[i:i + chunk_size]
                    full_response.append(chunk)

                    elapsed = time.time() - start_time
                    logger.info(
                        f"[BACKEND] Chunk sent at {elapsed:.3f}s: {chunk[:50] if chunk else '(empty)'}"
                    )

                    # SSE format: properly handle chunks that may contain newlines
                    lines = chunk.split('\n')
                    for j, line in enumerate(lines):
                        if line or j < len(lines) - 1:
                            yield f"data: {line}\n"

                    # Add blank line to signal end of message (SSE spec)
                    yield "\n"
                    await asyncio.sleep(0.01)

                # Save assistant message to conversation after streaming completes
                if conversation_id and full_response:
                    try:
                        sources = response.rag_quality.sources_covered if response.rag_quality else []
                        assistant_message = ConversationMessage(
                            type="assistant",
                            content=''.join(full_response),
                            timestamp=datetime.now().isoformat(),
                            data={
                                "classification": "streaming",
                                "sources": sources,
                                "disclaimer": safety_result.tier_disclaimer or "Always consult your healthcare provider."
                            }
                        )
                        conversation_manager.save_message(conversation_id, assistant_message)
                        logger.info(f"Saved streaming response to conversation {conversation_id}")
                    except Exception as e:
                        logger.error(f"Failed to save assistant message: {e}")

                # Send end event to signal completion
                yield "event: end\ndata: {}\n\n"
            except Exception as e:
                logger.error(f"Error in streaming response: {e}")
                yield f"data: Error: {str(e)}\n\n"
                yield "event: end\ndata: {}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up streaming query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred setting up streaming response.")


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
                "name": "PubMed Research Papers",
                "type": "pubmed_papers",
                "description": "PubMed research papers (39 chunks)"
            },
            {
                "name": "Device Manuals",
                "type": "device_manuals",
                "description": "CamAPS FX, Ypsomed, Libre 3 manuals"
            },
            {
                "name": "Clinical Guidelines",
                "type": "clinical_guidelines",
                "description": "ADA Standards of Care 2026, Australian Diabetes Guidelines"
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
        # Skip hourly analysis patterns - they're stored separately
        if pattern_type in ("highs_by_hour", "lows_by_hour"):
            continue
        if isinstance(pattern_data, dict) and pattern_data.get("detected"):
            # Use evidence array for description if available (more specific than default)
            evidence = pattern_data.get("evidence", [])
            if evidence and isinstance(evidence, list):
                description = " | ".join(evidence[:3])  # Use first 3 evidence items
            else:
                description = pattern_data.get("description", "Pattern detected")
            patterns_list.append({
                "type": pattern_type,
                "description": description,
                "confidence": round(pattern_data.get("confidence", 50), 2),
                "affected_readings": pattern_data.get("affected_readings", 0),
                "recommendation": pattern_data.get("recommendation", "Discuss with your healthcare team"),
            })

    # Extract hourly analysis data
    highs_by_hour = patterns_dict.get("highs_by_hour", {})
    lows_by_hour = patterns_dict.get("lows_by_hour", {})
    
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
        "hourly_analysis": {
            "highs": {
                "peak_hours": highs_by_hour.get("peak_hours", []),
                "peak_time_description": highs_by_hour.get("peak_time_description", ""),
                "evidence": highs_by_hour.get("evidence", []),
                "hourly_percentages": highs_by_hour.get("hourly_percentages", {}),
            },
            "lows": {
                "peak_hours": lows_by_hour.get("peak_hours", []),
                "peak_time_description": lows_by_hour.get("peak_time_description", ""),
                "evidence": lows_by_hour.get("evidence", []),
                "hourly_percentages": lows_by_hour.get("hourly_percentages", {}),
            },
        },
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

# Initialize user source manager
user_source_manager = UserSourceManager()

# Max upload size (50MB)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


# ============================================================================
# User Sources API
# ============================================================================

@app.post("/api/sources/upload", response_model=SourceUploadResponse)
async def upload_source(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    Upload a PDF to the user's source library.

    Accepts PDF files up to 50MB, validates, stores, and triggers indexing.
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file and check size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB"
        )

    # Validate PDF magic bytes
    if not content.startswith(b'%PDF'):
        raise HTTPException(status_code=400, detail="Invalid PDF file")

    try:
        # Add to user sources
        source = user_source_manager.add_source(file.filename, content)

        logger.info(f"Starting ingestion of {file.filename} into ChromaDB...")

        # Trigger indexing
        try:
            from agents.researcher_chromadb import ChromaDBBackend
            backend = ChromaDBBackend()
            backend.refresh_user_sources()
        except Exception as e:
            logger.warning(f"Indexing failed (will retry on next query): {e}")

        device_profile_complete = None
        device_profile = None
        if session_id:
            manager = UserDeviceManager(
                base_dir=Path(__file__).parent.parent / "data" / "users"
            )
            profile = manager.load_profile(session_id)
            if profile:
                device_profile = {
                    "pump": profile.pump,
                    "cgm": profile.cgm,
                    "timestamp": profile.timestamp,
                    "override_source": profile.override_source,
                }
                device_profile_complete = bool(profile.pump and profile.cgm)
            else:
                device_profile_complete = False

        return SourceUploadResponse(
            success=True,
            filename=source.filename,
            display_name=source.display_name,
            collection_key=source.collection_key,
            message="PDF uploaded and indexed successfully",
            device_profile_complete=device_profile_complete,
            device_profile=device_profile,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed")


@app.get("/api/sources/list")
async def list_sources():
    """
    List all knowledge sources (public + user).

    Returns dict with 'user_sources' and 'public_sources' arrays.
    """
    # Get user sources
    user_sources = user_source_manager.list_sources()

    # Get public sources from researcher
    try:
        from agents.researcher_chromadb import ChromaDBBackend
        backend = ChromaDBBackend()
        stats = backend.get_collection_stats()

        public_collections = [
            ('standards_of_care_2026', 'ADA Standards of Care'),
            ('australian_diabetes_guidelines', 'Australian Diabetes Guidelines'),
        ]

        public_sources = []
        for key, name in public_collections:
            if key in stats:
                public_sources.append({
                    'key': key,
                    'name': name,
                    'chunk_count': stats[key].get('count', 0),
                    'status': 'current'
                })
    except Exception as e:
        logger.error(f"Error loading public sources: {e}")
        public_sources = []

    return {
        'user_sources': [
            {
                'filename': s.filename,
                'display_name': s.display_name,
                'collection_key': s.collection_key,
                'uploaded_at': s.uploaded_at,
                'indexed': s.indexed,
                'chunk_count': s.chunk_count
            }
            for s in user_sources
        ],
        'public_sources': public_sources
    }


@app.delete("/api/sources/{filename}")
async def delete_source(request: Request, filename: str):
    """
    Delete a user-uploaded source.
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not await rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Get source before deleting (for collection key)
    source = user_source_manager.get_source_by_filename(filename)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Delete from ChromaDB
    try:
        from agents.researcher_chromadb import ChromaDBBackend
        backend = ChromaDBBackend()
        backend.delete_user_source_collection(source.collection_key)
    except Exception as e:
        logger.warning(f"Could not delete ChromaDB collection: {e}")

    # Delete file and metadata
    deleted = user_source_manager.delete_source(filename)

    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")

    return {"success": True, "message": f"Deleted {filename}"}


# Conversation Management Endpoints
@app.get("/api/conversations")
async def list_conversations() -> List[ConversationSummary]:
    """
    Get a list of all conversations with summaries.
    """
    return conversation_manager.get_conversation_summaries()


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> ConversationData:
    """
    Get the full message history for a specific conversation.
    """
    conversation = conversation_manager.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations")
async def create_conversation() -> dict:
    """
    Create a new conversation and return its ID.
    """
    conversation_id = conversation_manager.create_conversation()
    return {"conversationId": conversation_id}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Delete a conversation.
    """
    deleted = conversation_manager.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "message": "Conversation deleted"}


# ============================================================================
# Response Feedback Endpoint
# ============================================================================

# Feedback file path
FEEDBACK_FILE = PROJECT_ROOT / "data" / "analysis" / "response_quality.csv"


class FeedbackRequest(BaseModel):
    """Request model for response feedback."""
    message_id: str
    feedback: str  # 'helpful' or 'not-helpful'
    primary_source_type: Optional[str] = None
    knowledge_breakdown: Optional[dict] = None
    timestamp: str
    # Additional fields for learning loop
    query: Optional[str] = None
    response: Optional[str] = None
    sources_used: Optional[List[str]] = None
    rag_quality: Optional[dict] = None


@app.post("/api/feedback")
async def log_feedback(request: Request, feedback: FeedbackRequest):
    """
    Log user feedback on response quality.

    Tracks which source types (RAG vs parametric) get positive feedback
    for continuous improvement analysis.
    
    On negative feedback, triggers personalization learning loop.
    """
    import csv

    try:
        # Ensure directory exists
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Prepare row
        row = {
            'timestamp': feedback.timestamp,
            'message_id': feedback.message_id,
            'feedback': feedback.feedback,
            'primary_source_type': feedback.primary_source_type or 'unknown',
            'rag_ratio': feedback.knowledge_breakdown.get('rag_ratio', 0) if feedback.knowledge_breakdown else 0,
            'parametric_ratio': feedback.knowledge_breakdown.get('parametric_ratio', 0) if feedback.knowledge_breakdown else 0,
            'blended_confidence': feedback.knowledge_breakdown.get('blended_confidence', 0) if feedback.knowledge_breakdown else 0,
        }

        # Append to CSV
        file_exists = FEEDBACK_FILE.exists()
        with open(FEEDBACK_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        logger.info(f"Feedback logged: {feedback.feedback} for {feedback.primary_source_type}")
        
        # Trigger learning loop on negative feedback
        if feedback.feedback == 'not-helpful' and feedback.query:
            try:
                from agents.device_personalization import PersonalizationManager
                
                # Get session ID from request cookies or headers
                session_id = request.cookies.get('session_id', 'anonymous')
                
                personalization_manager = PersonalizationManager(config=app.state.config)
                personalization_manager.learn_from_negative_feedback(
                    query=feedback.query,
                    response=feedback.response or '',
                    sources=feedback.sources_used or [],
                    session_id=session_id,
                    rag_quality=feedback.rag_quality
                )
                logger.info(f"Triggered learning loop for negative feedback (session: {session_id[:8]})")
            except Exception as e:
                logger.warning(f"Could not trigger learning loop: {e}")
        
        return {"success": True}

    except Exception as e:
        logger.error(f"Failed to log feedback: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/feedback-stats")
async def get_feedback_stats():
    """Return feedback analytics and correlations."""
    try:
        if not FEEDBACK_FILE.exists():
            return {
                "total_responses": 0,
                "helpful_rate": 0.0,
                "source_performance": {},
                "rag_correlation": 0.0
            }

        import csv
        feedback_data = []
        with open(FEEDBACK_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                feedback_data.append({
                    'feedback': row['feedback'],
                    'primary_source_type': row['primary_source_type'],
                    'rag_ratio': float(row.get('rag_ratio', 0))
                })

        if not feedback_data:
            return {
                "total_responses": 0,
                "helpful_rate": 0.0,
                "source_performance": {},
                "rag_correlation": 0.0
            }

        total_responses = len(feedback_data)
        helpful_count = sum(1 for f in feedback_data if f['feedback'] == 'helpful')
        helpful_rate = helpful_count / total_responses if total_responses > 0 else 0.0

        # Source type performance
        source_counts = {}
        source_helpful = {}
        for feedback in feedback_data:
            source = feedback['primary_source_type']
            source_counts[source] = source_counts.get(source, 0) + 1
            if feedback['feedback'] == 'helpful':
                source_helpful[source] = source_helpful.get(source, 0) + 1

        source_performance = {}
        for source in source_counts:
            helpful = source_helpful.get(source, 0)
            total = source_counts[source]
            source_performance[source] = {
                "helpful_rate": helpful / total if total > 0 else 0.0,
                "total_responses": total
            }

        # RAG correlation (simplified - higher RAG ratio should correlate with helpfulness)
        rag_helpful = [f['rag_ratio'] for f in feedback_data if f['feedback'] == 'helpful']
        rag_not_helpful = [f['rag_ratio'] for f in feedback_data if f['feedback'] == 'not-helpful']
        
        avg_rag_helpful = sum(rag_helpful) / len(rag_helpful) if rag_helpful else 0.0
        avg_rag_not_helpful = sum(rag_not_helpful) / len(rag_not_helpful) if rag_not_helpful else 0.0
        
        rag_correlation = avg_rag_helpful - avg_rag_not_helpful  # Positive = RAG helps

        return {
            "total_responses": total_responses,
            "helpful_rate": round(helpful_rate, 3),
            "source_performance": source_performance,
            "rag_correlation": round(rag_correlation, 3)
        }

    except Exception as e:
        logger.error(f"Failed to get feedback stats: {e}")
        return {"error": str(e)}


@app.get("/api/experiments/status")
async def get_experiments_status():
    """
    Get live A/B test statistics with significance testing.
    
    Returns:
    - n per cohort
    - helpful_rate per cohort
    - p_value, t_statistic, Cohen's d
    - min_sample_size_reached flag
    - is_significant
    - winner ('control', 'treatment', or None)
    - recommendation text
    """
    try:
        analytics = ExperimentAnalytics(data_dir=Path(__file__).parent.parent / "data")
        stats = analytics.get_experiment_status(
            experiment_name="hybrid_vs_pure_rag",
            min_sample_size=620,
        )
        
        return {
            "experiment": stats.experiment_name,
            "control_n": stats.control_n,
            "treatment_n": stats.treatment_n,
            "control_helpful_rate": stats.control_helpful_rate,
            "treatment_helpful_rate": stats.treatment_helpful_rate,
            "min_sample_size": stats.min_sample_size,
            "min_sample_size_reached": stats.min_sample_size_reached,
            "p_value": stats.p_value,
            "t_statistic": stats.t_statistic,
            "cohens_d": stats.cohens_d,
            "is_significant": stats.is_significant,
            "effect_size": stats.effect_size_category,
            "winner": stats.winner,
            "recommendation": stats.recommendation,
        }
    except Exception as e:
        logger.error(f"Failed to get experiment status: {e}")
        return {"error": str(e)}


@app.post("/api/detect-devices")
async def detect_devices(request: Request, filename: str = None):
    """
    Detect pump and CGM devices from an uploaded PDF file.
    
    Query parameters:
    - filename: The filename of the uploaded PDF
    
    Returns:
    {
        "pump": "tandem" or null,
        "cgm": "dexcom" or null,
        "pump_confidence": 0.95 (0.0-1.0),
        "cgm_confidence": 0.85 (0.0-1.0)
    }
    """
    try:
        if not filename:
            raise ValueError("filename parameter required")
        
        # Import here to avoid circular dependency
        from agents.device_detection import DeviceDetector
        from pathlib import Path
        
        # Get the file path from the uploaded sources
        sources_dir = Path(__file__).parent.parent / "data" / "sources"
        file_path = sources_dir / filename
        
        if not file_path.exists():
            raise ValueError(f"File not found: {filename}")
        
        # Create detector and detect devices
        detector = DeviceDetector()
        results = detector.detect_from_file(str(file_path))
        
        return {
            "pump": results.get("pump"),
            "cgm": results.get("cgm"),
            "pump_confidence": results.get("pump_confidence", 0.0),
            "cgm_confidence": results.get("cgm_confidence", 0.0),
        }
    except Exception as e:
        logger.error(f"Failed to detect devices: {e}")
        return {
            "pump": None,
            "cgm": None,
            "pump_confidence": 0.0,
            "cgm_confidence": 0.0,
            "error": str(e)
        }


@app.get("/api/devices/profile")
async def get_device_profile(session_id: str):
    """
    Return the saved device profile for a session.

    Query parameters:
    - session_id: The user session identifier
    """
    try:
        manager = UserDeviceManager(
            base_dir=Path(__file__).parent.parent / "data" / "users"
        )
        profile = manager.load_profile(session_id)
        if not profile:
            return {
                "exists": False,
                "is_complete": False,
                "pump": None,
                "cgm": None,
                "timestamp": None,
                "override_source": None,
            }

        return {
            "exists": True,
            "is_complete": bool(profile.pump and profile.cgm),
            "pump": profile.pump,
            "cgm": profile.cgm,
            "timestamp": profile.timestamp,
            "override_source": profile.override_source,
        }
    except Exception as e:
        logger.error(f"Failed to get device profile: {e}")
        return {"exists": False, "is_complete": False, "error": str(e)}


@app.post("/api/devices/override")
async def set_device_override(request: Request):
    """
    Override auto-detected devices with user-confirmed selections.
    
    Expected body:
    {
        "session_id": "session-abc123",
        "pump": "tandem",
        "cgm": "dexcom"
    }

    Stores user override with override_source='user'.
    Returns the saved device profile.
    """
    try:
        body = await request.json()
        session_id = body.get("session_id")
        pump = body.get("pump")
        cgm = body.get("cgm")

        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")

        manager = UserDeviceManager(
            base_dir=Path(__file__).parent.parent / "data" / "users"
        )

        profile = manager.apply_user_override(session_id, pump=pump, cgm=cgm)

        return {
            "success": True,
            "session_id": profile.session_id,
            "pump": profile.pump,
            "cgm": profile.cgm,
            "timestamp": profile.timestamp,
            "override_source": profile.override_source,
        }
    except Exception as e:
        logger.error(f"Failed to set device override: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# Glucose Unit Settings Endpoints
# ============================================

@app.get("/api/settings/glucose-unit")
async def get_glucose_unit():
    """Get the current glucose unit preference."""
    try:
        config_file = Path(__file__).parent.parent / "config" / "user_profile.json"
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                profile = json.load(f)
                glucose_unit = profile.get("glucose_unit", "mmol/L")
        else:
            glucose_unit = "mmol/L"
        
        return {"glucose_unit": glucose_unit}
    except Exception as e:
        logger.error(f"Failed to get glucose unit: {e}")
        return {"glucose_unit": "mmol/L"}


@app.post("/api/settings/glucose-unit")
async def set_glucose_unit(body: dict):
    """Set the glucose unit preference."""
    try:
        glucose_unit = body.get("glucose_unit", "mmol/L")
        
        # Validate the glucose unit
        if glucose_unit not in ("mmol/L", "mg/dL"):
            raise HTTPException(status_code=400, detail="Invalid glucose_unit. Must be 'mmol/L' or 'mg/dL'")
        
        config_file = Path(__file__).parent.parent / "config" / "user_profile.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing profile or create new one
        if config_file.exists():
            with open(config_file, 'r') as f:
                profile = json.load(f)
        else:
            profile = {
                "version": "1.0.0",
                "created_at": datetime.now().isoformat()
            }
        
        # Update glucose unit
        profile["glucose_unit"] = glucose_unit
        profile["updated_at"] = datetime.now().isoformat()
        
        # Save profile
        with open(config_file, 'w') as f:
            json.dump(profile, f, indent=2)
        
        logger.info(f"Glucose unit updated to: {glucose_unit}")
        return {"success": True, "glucose_unit": glucose_unit}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set glucose unit: {e}")
        return {"success": False, "error": str(e)}


# Mount static files
web_dir = Path(__file__).parent
static_dir = web_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.app:app",  # Import string, not app object
        host="0.0.0.0",
        port=8001,  # Changed from 8000 to 8001
        reload=False,  # Disable reload in production
        log_level="info"
    )
