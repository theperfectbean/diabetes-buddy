"""
Unified Agent for Diabetes Buddy

Single agent that handles all queries without routing.
Every query gets both user's Glooko data and knowledge base results.
The LLM decides what's relevant.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
import re
import sys
import yaml
import logging

from .experimentation import ExperimentManager, CohortConfig
from .response_quality_evaluator import ResponseQualityEvaluator
from .router_agent import RouterAgent, RouterContext

logger = logging.getLogger(__name__)

from .llm_provider import LLMFactory, GenerationConfig, LLMProviderError
from .session_manager import SessionManager
from .source_manager import UserSourceManager

# Import researcher for knowledge base search
try:
    from .researcher_chromadb import ResearcherAgent

    CHROMADB_AVAILABLE = True
except ImportError:
    from .researcher import ResearcherAgent

    CHROMADB_AVAILABLE = False


@dataclass
class RAGQualityAssessment:
    """Assessment of RAG retrieval quality for hybrid decision-making."""

    chunk_count: int
    avg_confidence: float
    max_confidence: float
    min_confidence: float
    sources_covered: list[str]  # Unique source names
    source_diversity: int  # Count of unique sources
    topic_coverage: str  # 'sufficient', 'partial', 'sparse'

    @property
    def is_sufficient(self) -> bool:
        """RAG is sufficient if ≥3 chunks with avg confidence ≥0.7."""
        return (
            self.chunk_count >= 3
            and self.avg_confidence >= 0.7
            and self.topic_coverage == "sufficient"
        )


@dataclass
class RAGQualityMetrics:
    """Metrics about RAG retrieval quality for response transparency."""

    chunk_count: int
    avg_confidence: float
    sources_covered: list[str]
    topic_coverage: str  # 'sufficient', 'partial', 'sparse'


@dataclass
class KnowledgeBreakdown:
    """Breakdown of knowledge sources used in response for UI transparency."""

    rag_confidence: float  # Average confidence from RAG chunks (0.0-1.0)
    parametric_confidence: float  # Fixed at 0.6 for parametric content
    blended_confidence: float  # Weighted average based on content ratio
    rag_ratio: float  # % of response from RAG (0.0-1.0)
    parametric_ratio: float  # % of response from parametric (0.0-1.0)
    primary_source_type: str  # 'rag' | 'parametric' | 'hybrid' | 'glooko'


@dataclass
class UnifiedResponse:
    """Response from the unified agent."""

    success: bool
    answer: str
    sources_used: list[str]  # Which sources contributed: "rag", "parametric", "glooko"
    glooko_data_available: bool
    disclaimer: str = ""
    priority: str = "NORMAL"  # "NORMAL", "CRITICAL" for emergency detection
    cohort: Optional[str] = None
    # Hybrid RAG + parametric knowledge fields
    rag_quality: Optional[RAGQualityMetrics] = None
    requires_enhanced_safety_check: bool = False
    # Knowledge source transparency for UI
    knowledge_breakdown: Optional[KnowledgeBreakdown] = None
    # LLM provider information
    llm_info: Optional[dict] = None  # {provider, model, tokens_used, estimated_cost, routing_reason}
    response_time: Optional[dict] = None  # {retrieval_ms, synthesis_ms, total_ms}
    # Quality evaluation score (async, may be None initially)
    quality_score: Optional[dict] = None  # Quality evaluation results
    # Safety fallback information
    error_type: Optional[str] = None  # "safety_fallback" when dosing query fails


class UnifiedAgent:
    """
    Single agent that handles all queries without classification/routing.

    For every query:
    1. Load user's Glooko data (if available)
    2. Search knowledge base for relevant context
    3. Give LLM everything and let it answer naturally
    """

    # Patterns for detecting dangerous queries
    DOSING_QUERY_PATTERNS = [
        r"\bhow much insulin\b",
        r"\binsulin dose\b",
        r"\bbolus calculation\b",
        r"\bcalculate.*bolus\b",
        r"\bcarb ratio\b",
        r"\binsulin.*carb.*ratio\b",
        r"\bcalculate.*insulin\b",
        r"\bdose.*carbs?\b",
        r"\binsulin.*for.*carbs?\b",
    ]

    PRODUCT_CONFIG_PATTERNS = [
        r"\b(configure|setup|install|set up)\s+(autosens|autotune|extended bolus|temp basal|basal rate|carb ratio|correction factor|sensitivity factor)\b",
        r"\bhow.*(configure|setup|install|set up).*(pump|cgm|sensor|loop|openaps|androidaps|camaps|control.?iq|omnipod|tandem|medtronic)\b",
        r"\b(configure|setup|install|set up).*(pump|cgm|sensor|loop|openaps|androidaps|camaps|control.?iq|omnipod|tandem|medtronic)\b",
    ]

    # Emergency detection keywords
    EMERGENCY_KEYWORDS = [
        # Hypoglycemia terms
        "low blood sugar",
        "hypo",
        "shaking",
        "confusion",
        "unconscious",
        "blood sugar dropping",
        "feeling shaky",
        "cold sweat",
        "difficulty speaking",
        "severe headache",
        "can't think straight",
        "slurred speech",
        "extreme weakness",
        "pale skin",
        "rapid heartbeat",
        # Severe hyperglycemia / DKA
        "dka",
        "ketones",
        "vomiting",
        "fruity breath",
        "ketoacidosis",
        "high ketones",
        "acetone breath",
        "rapid breathing",
        "confusion and ketones",
        "severe hyperglycemia",
        "blood sugar over 300",
        "blood sugar over 400",
        # Acute complications
        "seizure",
        "stroke symptoms",
        "chest pain",
        "heart attack",
        "severe abdominal pain",
        "unconscious",
        "seizure activity",
        "can't wake up",
        "severe pain",
        "difficulty breathing",
        "shortness of breath",
        "severe nausea",
        # Emergency context
        "emergency",
        "call ambulance",
        "medical help",
        "life threatening",
        "immediately",
        "right now",
        "asap",
        "urgent",
        "critical condition",
    ]

    # Emergency detection patterns (regex)
    EMERGENCY_PATTERNS = [
        r"\b(severe|extreme|critical|life.threatening)\b.*\b(pain|symptoms?|condition)\b",
        r"\b(immediately|right now|asap|urgent)\b.*\b(help|attention|care)\b",
        r"\b(can\'?t|cannot)\b.*\b(breathe|see|speak|move|wake)\b",
        r"\b(blood sugar|glucose)\b.*\b(under|below)\b.*\b(50|40|30|20)\b",
        r"\b(blood sugar|glucose)\b.*\b(over|above)\b.*\b(500|600|700)\b",
    ]

    def __init__(self, project_root: Optional[str] = None):
        self.llm = LLMFactory.get_provider()

        if project_root is None:
            project_root = Path(__file__).parent.parent
        else:
            project_root = Path(project_root)

        self.project_root = project_root
        self.analysis_dir = project_root / "data" / "analysis"

        # Load hybrid knowledge configuration
        self.config = self._load_hybrid_config()

        # Initialize experimentation manager (optional)
        self.experiment_manager: Optional[ExperimentManager] = None
        experimentation_config = self.config.get("experimentation", {})
        if experimentation_config.get("enabled", False):
            try:
                storage_dir = experimentation_config.get("storage_dir", "data")
                self.experiment_manager = ExperimentManager(
                    self.config,
                    storage_dir=self.project_root / storage_dir,
                )
            except Exception as exc:
                logger.warning(
                    f"Experimentation disabled due to initialization error: {exc}"
                )
                self.experiment_manager = None

        # Initialize knowledge base researcher
        self.researcher = ResearcherAgent(project_root=project_root)
        logger.debug(
            f"Researcher initialized, use_chromadb: {getattr(self.researcher, 'use_chromadb', 'unknown')}"
        )
        if hasattr(self.researcher, "backend"):
            logger.debug(f"Researcher has backend: {type(self.researcher.backend)}")
        else:
            logger.debug("Researcher has no backend")

        # Initialize source manager for device detection
        try:
            from .source_manager import UserSourceManager
            self.source_manager = UserSourceManager(project_root=project_root)
            logger.debug("Source manager initialized for device detection")
        except Exception as e:
            logger.warning(f"Source manager not available: {e}")
            self.source_manager = None

        # Initialize quality evaluator
        quality_config = self.config.get("quality_evaluation", {})
        self.quality_evaluator: Optional[ResponseQualityEvaluator] = None
        if quality_config.get("enabled", True):
            try:
                self.quality_evaluator = ResponseQualityEvaluator(
                    config=quality_config,
                    llm_provider=self.llm
                )
                logger.debug("Quality evaluator initialized")
            except Exception as e:
                logger.warning(f"Quality evaluator not available: {e}")
                self.quality_evaluator = None
        
        # Initialize router agent for Agentic RAG
        try:
            self.router = RouterAgent()
            logger.debug("Router agent initialized for Agentic RAG")
        except Exception as e:
            logger.warning(f"Router agent not available: {e}")
            self.router = None

    def _load_hybrid_config(self) -> dict:
        """Load hybrid knowledge configuration from YAML file."""
        config_path = self.project_root / "config" / "hybrid_knowledge.yaml"

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")

        # Validate configuration
        self._validate_config(config)

        return config

    def _validate_config(self, config: dict) -> None:
        """Validate configuration values and raise errors for invalid thresholds."""
        # Check required sections
        required_sections = [
            "rag_quality",
            "parametric_usage",
            "safety",
            "emergency_detection",
            "logging",
            "knowledge_monitoring",
        ]
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Validate rag_quality
        rq = config["rag_quality"]
        if not isinstance(rq.get("min_chunks"), int) or rq["min_chunks"] < 1:
            raise ValueError("rag_quality.min_chunks must be an integer >= 1")
        if not isinstance(rq.get("min_confidence"), (int, float)) or not (
            0.0 <= rq["min_confidence"] <= 1.0
        ):
            raise ValueError(
                "rag_quality.min_confidence must be a float between 0.0 and 1.0"
            )
        if not isinstance(rq.get("min_sources"), int) or rq["min_sources"] < 1:
            raise ValueError("rag_quality.min_sources must be an integer >= 1")
        if not isinstance(rq.get("min_chunk_confidence"), (int, float)) or not (
            0.0 <= rq["min_chunk_confidence"] <= 1.0
        ):
            raise ValueError(
                "rag_quality.min_chunk_confidence must be a float between 0.0 and 1.0"
            )

        # Validate parametric_usage
        pu = config["parametric_usage"]
        if not isinstance(pu.get("max_ratio"), (int, float)) or not (
            0.0 <= pu["max_ratio"] <= 1.0
        ):
            raise ValueError(
                "parametric_usage.max_ratio must be a float between 0.0 and 1.0"
            )
        if not isinstance(pu.get("confidence_score"), (int, float)) or not (
            0.0 <= pu["confidence_score"] <= 1.0
        ):
            raise ValueError(
                "parametric_usage.confidence_score must be a float between 0.0 and 1.0"
            )

        # Validate safety
        safety = config["safety"]
        if not isinstance(safety.get("enhanced_check_threshold"), (int, float)) or not (
            0.0 <= safety["enhanced_check_threshold"] <= 1.0
        ):
            raise ValueError(
                "safety.enhanced_check_threshold must be a float between 0.0 and 1.0"
            )

        # Validate emergency_detection
        ed = config["emergency_detection"]
        if not isinstance(ed.get("enabled"), bool):
            raise ValueError("emergency_detection.enabled must be a boolean")
        if "severity_thresholds" in ed:
            st = ed["severity_thresholds"]
            for level in ["critical", "high", "medium"]:
                if (
                    level in st
                    and not isinstance(st[level], (int, float))
                    or not (0.0 <= st[level] <= 1.0)
                ):
                    raise ValueError(
                        f"emergency_detection.severity_thresholds.{level} must be a float between 0.0 and 1.0"
                    )

        # Validate logging
        logging_config = config["logging"]
        if logging_config.get("level") not in [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]:
            raise ValueError(
                "logging.level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        if (
            not isinstance(logging_config.get("max_size_mb"), int)
            or logging_config["max_size_mb"] < 1
        ):
            raise ValueError("logging.max_size_mb must be an integer >= 1")
        if (
            not isinstance(logging_config.get("backup_count"), int)
            or logging_config["backup_count"] < 1
        ):
            raise ValueError("logging.backup_count must be an integer >= 1")

        # Validate knowledge_monitoring
        km = config["knowledge_monitoring"]
        if (
            not isinstance(km.get("staleness_threshold_days"), int)
            or km["staleness_threshold_days"] < 1
        ):
            raise ValueError(
                "knowledge_monitoring.staleness_threshold_days must be an integer >= 1"
            )
        if (
            not isinstance(km.get("critical_threshold_days"), int)
            or km["critical_threshold_days"] < 1
        ):
            raise ValueError(
                "knowledge_monitoring.critical_threshold_days must be an integer >= 1"
            )

    def process_stream(
        self,
        query: str,
        session_id: Optional[str] = None,
        conversation_history: Optional[list] = None,
    ):
        """
        Process a query with streaming response using two-stage RAG + parametric approach.

        Stage 1: Always query RAG first
        Stage 2: Assess RAG quality - if sparse, augment with LLM parametric knowledge

        Args:
            query: User's question
            session_id: Optional session ID for tracking
            conversation_history: List of previous exchanges for context.
                Each exchange is a dict with 'query' and 'response' keys.

        Yields:
            str: Chunks of the response as they become available
        """
        if conversation_history is None:
            conversation_history = []
        # Check for emergency symptoms
        is_emergency, severity = self._detect_emergency_query(query)
        if is_emergency:
            self._log_emergency_query(query, severity)
            template_key = (
                severity.lower()
                if severity in ["CRITICAL", "HIGH", "MEDIUM"]
                else "critical"
            )
            response_template = self.config["emergency_detection"][
                "response_templates"
            ].get(
                template_key,
                "⚠️ MEDICAL EMERGENCY detected. This may be a medical emergency. Call emergency services if symptoms worsen.",
            )
            yield f"{response_template}\n\n"
            yield "Please seek immediate medical attention for severe symptoms. I'm not a substitute for emergency care.\n\n### Sources\n- Emergency safety guidelines"
            return

        cohort = self._get_cohort_assignment(session_id)
        self._log_experiment_assignment(session_id, query, cohort)
        control_mode = cohort == "control"

        rag_config = dict(self.config["rag_quality"])
        parametric_config = dict(self.config["parametric_usage"])
        if control_mode and self.experiment_manager:
            cohort_config = self.experiment_manager.experiments.get(
                "hybrid_vs_pure_rag"
            )
            if cohort_config is None:
                cohort_config = CohortConfig(
                    name="hybrid_vs_pure_rag",
                    cohorts={"control": 50, "treatment": 50},
                )
            rag_config, parametric_config = cohort_config.apply_control_constraints(
                rag_config,
                parametric_config,
            )

        # Step 1: Load user's Glooko data (always try)
        glooko_context = self._load_glooko_context()

        # Step 1.5: Detect user's devices for device-aware prompting
        user_devices = []
        if self.source_manager:
            try:
                detected = self.source_manager.get_user_devices()
                user_devices = [d["name"] for d in detected]
                if user_devices:
                    logger.info(f"Detected user devices (streaming): {user_devices}")
            except Exception as e:
                logger.warning(f"Could not detect user devices: {e}")

        # Step 2: Get raw RAG results for quality assessment
        MIN_CHUNK_CONFIDENCE = rag_config["min_chunk_confidence"]
        try:
            raw_results = self.researcher.query_knowledge(
                query, top_k=5, session_id=session_id
            )
            filtered_results = [
                r for r in raw_results if r.confidence >= MIN_CHUNK_CONFIDENCE
            ]
        except Exception:
            filtered_results = []

        # Step 3: Assess RAG quality
        rag_quality = self._assess_rag_quality(filtered_results, query)

        # Step 4: Format RAG context from filtered results
        kb_context = None
        if filtered_results:
            kb_context = ""
            for r in filtered_results:
                kb_context += f"---\n{r.quote[:600]}\n\n"
            kb_context = kb_context.strip() if kb_context.strip() else None

        # Step 5: Choose prompt type based on RAG quality
        sources_for_prompt = self._format_sources_for_prompt(
            filtered_results,
            glooko_context,
        )
        if rag_quality.is_sufficient or control_mode:
            # RAG is sufficient - use standard prompt
            prompt = self._build_prompt(
                query,
                glooko_context,
                kb_context,
                rag_quality.max_confidence,
                sources_for_prompt,
                conversation_history=conversation_history,
                user_devices=user_devices,
            )
        else:
            # RAG is sparse/partial - use hybrid prompt with parametric knowledge
            prompt = self._build_hybrid_prompt(
                query,
                kb_context,
                rag_quality,
                glooko_context,
                sources_for_prompt,
                conversation_history=conversation_history,
                user_devices=user_devices,
            )

        # Step 6: Generate streaming response
        try:
            for chunk in self.llm.generate_text_stream(
                prompt=prompt,
                config=GenerationConfig(temperature=0.3, max_tokens=1000),
            ):
                yield chunk

        except Exception as e:
            yield f"An error occurred while processing your question: {str(e)}"

    def _detect_dosing_query(self, query: str) -> bool:
        """Detect if query is asking for specific dosing advice."""
        query_lower = query.lower()
        for pattern in self.DOSING_QUERY_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def _detect_product_config_query(self, query: str) -> bool:
        """Detect if query is asking for product-specific configuration."""
        query_lower = query.lower()
        for pattern in self.PRODUCT_CONFIG_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def _detect_emergency_query(self, query: str) -> tuple[bool, str]:
        """Detect if query describes a potential medical emergency and return severity level."""
        if not self.config.get("emergency_detection", {}).get("enabled", True):
            return False, "NORMAL"

        query_lower = query.lower()
        detected_keywords = []

        # Check keywords
        for keyword in self.EMERGENCY_KEYWORDS:
            if keyword in query_lower:
                detected_keywords.append(keyword)

        # Check regex patterns
        for pattern in self.EMERGENCY_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                detected_keywords.append(f"pattern:{pattern}")

        if not detected_keywords:
            return False, "NORMAL"

        # Calculate severity score based on number of matches
        severity_score = min(len(detected_keywords) / 3.0, 1.0)  # Normalize to 0-1

        # Determine severity level
        thresholds = self.config["emergency_detection"]["severity_thresholds"]
        if severity_score >= thresholds["critical"]:
            return True, "CRITICAL"
        elif severity_score >= thresholds["high"]:
            return True, "HIGH"
        elif severity_score >= thresholds["medium"]:
            return True, "MEDIUM"
        else:
            return True, "LOW"

    def _get_cohort_assignment(self, session_id: Optional[str]) -> Optional[str]:
        if not self.experiment_manager:
            return None
        session_key = session_id or "anonymous"
        try:
            return self.experiment_manager.get_cohort_assignment(session_key)
        except Exception as exc:
            logger.warning(f"Failed to assign cohort: {exc}")
            return None

    def _log_experiment_assignment(
        self, session_id: Optional[str], query: str, cohort: Optional[str]
    ) -> None:
        if not self.experiment_manager or not cohort:
            return
        session_key = session_id or "anonymous"
        try:
            self.experiment_manager.log_assignment(
                session_key,
                query,
                cohort,
                metadata={"mode": "stream"},
            )
        except Exception as exc:
            logger.warning(f"Failed to log experiment assignment: {exc}")

    def _select_llm_provider(
        self,
        query: str,
        safety_level: str = "NORMAL",
        rag_quality: Optional[RAGQualityAssessment] = None,
        estimated_input_tokens: int = 0,
    ) -> tuple[str, str, str]:
        """
        Intelligently select LLM provider and model based on query characteristics.

        **ROUTING ARCHITECTURE:**
        - All queries route to Groq (no provider switching)
        - Safety filtering handled by Safety Auditor (pre/post processing), not LLM choice

        Returns:
            (provider_name, model_name, routing_reason)

        Routing decision tree:
        1. **Device manual queries** → Groq GPT-OSS-20B (fast, cheap)
        2. **Simple factual** → Groq GPT-OSS-20B (quick responses)
        3. **Glooko analysis** → Groq GPT-OSS-120B (complex reasoning with caching)
        4. **Clinical synthesis** → Groq GPT-OSS-120B (knowledge base integration)
        5. **Complex multi-source** → Groq GPT-OSS-120B (RAG with deep reasoning)
        6. **Default** → Groq GPT-OSS-20B (default model for any query type)

        Note: Safety-critical queries (dosing, emergency) are protected by Safety Auditor,
              not by restricting LLM choice. This allows faster response times and cost savings
              while maintaining the same safety guarantees.
        """
        query_lower = query.lower()
        smart_routing_enabled = os.environ.get("ENABLE_SMART_ROUTING", "true").lower() == "true"

        # If smart routing is disabled, use configured provider
        if not smart_routing_enabled:
            return "groq", "groq/openai/gpt-oss-20b", "Smart routing disabled, using groq"

        # GROQ-FIRST ROUTING (all queries)
        # Device manual queries → GPT-OSS-20B (fast, low cost)
        device_keywords = ["pump", "cgm", "tandem", "dexcom", "libre", "omnipod", "medtronic", "sensor", "device", "manual"]
        if any(kw in query_lower for kw in device_keywords):
            return "groq", "groq/openai/gpt-oss-20b", "Device manual query → Groq 20B (fast, cost-optimized)"

        # Simple factual queries → GPT-OSS-20B
        simple_patterns = ["what is", "how do i", "explain", "define", "tell me about", "where is"]
        if any(pattern in query_lower for pattern in simple_patterns):
            if estimated_input_tokens < 1000:
                return "groq", "groq/openai/gpt-oss-20b", "Simple factual query → Groq 20B"

        # Glooko analysis queries → GPT-OSS-120B with caching
        glooko_keywords = ["pattern", "trend", "analyze", "my data", "time in range", "tir", "average", "glucose trend"]
        if any(kw in query_lower for kw in glooko_keywords):
            return "groq", "groq/openai/gpt-oss-120b", "Glooko analysis → Groq 120B with caching"

        # Clinical synthesis queries → GPT-OSS-120B with caching
        clinical_keywords = ["ada", "guideline", "research", "compare", "studies", "evidence-based", "clinical"]
        if any(kw in query_lower for kw in clinical_keywords):
            # Enable caching for guideline queries
            os.environ["GROQ_ENABLE_CACHING"] = "true"
            return "groq", "groq/openai/gpt-oss-120b", "Clinical synthesis → Groq 120B with prompt caching"

        # Multi-source complex queries (RAG heavy) → GPT-OSS-120B
        if rag_quality and rag_quality.chunk_count >= 5:
            return "groq", "groq/openai/gpt-oss-120b", "Complex multi-source query → Groq 120B"

        # DEFAULT: Use Groq 20B for any other query
        return "groq", "groq/openai/gpt-oss-20b", "General query → Groq 20B (default)"

    def _generate_with_fallback(
        self,
        prompt: str,
        primary_provider: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> tuple[str, dict]:
        """
        Generate text with retry on transient errors.

        GROQ-ONLY ARCHITECTURE:
        - Attempts Groq with retry + exponential backoff
        - No provider switching or fallback

        Args:
            prompt: Text prompt
            primary_provider: Provider to try first (defaults to groq)
            config: Generation configuration

        Returns:
            (answer, llm_info) where llm_info includes:
            - intended_provider: What we tried to use
            - actual_provider: What actually answered
            - model: Model name used
            - tokens_used: {"input": N, "output": M}
            - estimated_cost: Float cost
            - routing_reason: Why this provider was selected
        """
        config = config or GenerationConfig()
        max_retries = int(os.environ.get("GROQ_MAX_RETRIES", os.environ.get("GROQ_FALLBACK_RETRIES", "3")))
        base_delay = float(os.environ.get("GROQ_RETRY_BASE_DELAY", "1"))

        # Determine primary provider to use
        if not primary_provider:
            primary_provider = "groq"

        llm_info = {
            "intended_provider": primary_provider,
            "actual_provider": primary_provider,
            "provider": primary_provider,
            "model": "",
            "tokens_used": {"input": 0, "output": 0},
            "estimated_cost": 0.0,
            "routing_reason": "groq_only_strategy",
            "fallback_used": False,
            "fallback_reason": None,
        }

        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting {primary_provider} (attempt {attempt + 1}/{max_retries})"
                )

                answer = self.llm.generate_text(
                    prompt=prompt,
                    config=config,
                )

                llm_info["actual_provider"] = primary_provider
                llm_info["provider"] = primary_provider
                if hasattr(self.llm, "model_name"):
                    llm_info["model"] = self.llm.model_name
                elif hasattr(self.llm, "model"):
                    llm_info["model"] = self.llm.model

                logger.info(f"✓ {primary_provider} succeeded")
                return answer, llm_info

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"{primary_provider} failed (attempt {attempt + 1}/{max_retries}): {last_error}"
                )

                is_retriable = any(
                    kw in last_error.lower()
                    for kw in [
                        "rate limit",
                        "429",
                        "timeout",
                        "503",
                        "connection",
                        "overloaded",
                        "temporarily unavailable",
                        "api error",
                        "503 service unavailable",
                    ]
                )

                if not is_retriable or attempt == max_retries - 1:
                    break

                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying after {delay:.1f}s backoff")
                time.sleep(delay)

        raise LLMProviderError(
            f"Groq failed after {max_retries} attempts. Last error: {last_error}"
        )

    def _is_dosing_query(self, query: str) -> bool:
        """
        Detect if query is about insulin dosing (safety-critical).
        
        Returns True if query contains dosing keywords AND numbers.
        
        Args:
            query: User's question text
            
        Returns:
            bool: True if this is a dosing query
        """
        query_lower = query.lower()
        
        # Dosing keywords
        dosing_keywords = [
            'insulin', 'dose', 'dosing', 'bolus', 'basal', 
            'correction', 'carb ratio', 'units', 'units/hour'
        ]
        
        # Check if query contains a dosing keyword
        has_dosing_keyword = any(
            keyword in query_lower for keyword in dosing_keywords
        )
        
        # Check if query contains numbers (amounts, blood sugars, carbs)
        has_numbers = bool(re.search(r'\d+', query))
        
        return has_dosing_keyword and has_numbers

    def _get_dosing_fallback_message(self) -> str:
        """Get the emergency fallback message for dosing query failures."""
        return """I'm having trouble connecting to our system right now. For insulin dosing questions, please:

1. **Use your pump's bolus calculator/wizard feature** - It calculates based on your individual settings
2. **Contact your diabetes care team immediately** - They can provide personalized guidance
3. **If this is an emergency** (blood sugar >300 or <70), call your healthcare provider or 911

**Your safety is the priority. Never guess on insulin doses - always get professional guidance.**"""

    def _log_safety_fallback(self, query: str, error_type: str) -> None:
        """
        Log when safety fallback is used for dosing query failure.
        
        Args:
            query: The user's query
            error_type: Type of error that triggered fallback
        """
        import csv
        from datetime import datetime
        
        safety_log = self.analysis_dir / "safety_fallback_log.csv"
        
        # Create file with headers if it doesn't exist
        if not safety_log.exists():
            with open(safety_log, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "query",
                    "error_type",
                    "fallback_triggered"
                ])
        
        # Append the fallback event
        with open(safety_log, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                query,
                error_type,
                "true"
            ])

    def _log_emergency_query(self, query: str, severity: str) -> None:
        """Log emergency query to CSV for review."""
        import csv
        from datetime import datetime

        emergency_csv = self.analysis_dir / "emergency_queries.csv"

        # Detect which keywords/patterns triggered the emergency
        detected_keywords = []
        query_lower = query.lower()

        for keyword in self.EMERGENCY_KEYWORDS:
            if keyword in query_lower:
                detected_keywords.append(keyword)

        for pattern in self.EMERGENCY_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                detected_keywords.append(f"pattern:{pattern}")

        # Calculate severity score based on number of matches
        severity_score = min(len(detected_keywords) / 3.0, 1.0)  # Normalize to 0-1

        # Create file with headers if it doesn't exist
        if not emergency_csv.exists():
            with open(emergency_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "query",
                        "severity_level",
                        "detected_keywords",
                        "severity_score",
                    ]
                )

        # Append the query with enhanced data
        with open(emergency_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now().isoformat(),
                    query,
                    severity,
                    ";".join(detected_keywords),
                    f"{severity_score:.2f}",
                ]
            )

    def process(
        self,
        query: str,
        session_id: Optional[str] = None,
        conversation_history: Optional[list] = None,
    ) -> UnifiedResponse:
        """
        Process any query with full context using two-stage RAG + parametric approach.

        Stage 1: Always query RAG first
        Stage 2: Assess RAG quality - if sparse, augment with LLM parametric knowledge

        Args:
            query: User's question (any type)
            session_id: Optional session ID for tracking
            conversation_history: List of previous exchanges for context.
                Each exchange is a dict with 'query' and 'response' keys.

        Returns:
            UnifiedResponse with answer and metadata including RAG quality metrics
        """
        if conversation_history is None:
            conversation_history = []
        
        logger.info(f"[UNIFIED] Processing query: {query[:100]}")
        
        # Initialize router context for Agentic RAG
        router_context = None
        if self.router:
            try:
                router_context = self.router.analyze_query(query)
                logger.info(
                    f"[AGENTIC RAG] Router context: automation={router_context.automation_mode.value}, "
                    f"devices={router_context.devices_mentioned}, "
                    f"exclude={router_context.exclude_sources}"
                )
            except Exception as e:
                logger.warning(f"Router analysis failed: {e}")
                router_context = None
        
        # Check for emergency symptoms
        is_emergency, severity = self._detect_emergency_query(query)
        if is_emergency:
            self._log_emergency_query(query, severity)
            template_key = (
                severity.lower()
                if severity in ["CRITICAL", "HIGH", "MEDIUM"]
                else "critical"
            )
            response_template = self.config["emergency_detection"][
                "response_templates"
            ].get(
                template_key,
                "⚠️ MEDICAL EMERGENCY detected. This may be a medical emergency. Call emergency services if symptoms worsen.",
            )
            return UnifiedResponse(
                success=True,
                answer=f"{response_template}\n\nPlease seek immediate medical attention for severe symptoms. I'm not a substitute for emergency care.\n\n### Sources\n- Emergency safety guidelines",
                sources_used=[],
                glooko_data_available=False,
                disclaimer=response_template,
                priority=severity,
            )

        cohort = self._get_cohort_assignment(session_id)
        self._log_experiment_assignment(session_id, query, cohort)
        control_mode = cohort == "control"

        rag_config = dict(self.config["rag_quality"])
        parametric_config = dict(self.config["parametric_usage"])
        if control_mode and self.experiment_manager:
            cohort_config = self.experiment_manager.experiments.get(
                "hybrid_vs_pure_rag"
            )
            if cohort_config is None:
                cohort_config = CohortConfig(
                    name="hybrid_vs_pure_rag",
                    cohorts={"control": 50, "treatment": 50},
                )
            rag_config, parametric_config = cohort_config.apply_control_constraints(
                rag_config,
                parametric_config,
            )

        # Step 1: Load user's Glooko data (always try)
        glooko_context = self._load_glooko_context()
        glooko_available = glooko_context is not None

        # Step 1.5: Detect user's devices for device-aware prompting
        user_devices = []
        if self.source_manager:
            try:
                detected = self.source_manager.get_user_devices()
                user_devices = [d["name"] for d in detected]
                if user_devices:
                    logger.info(f"Detected user devices: {user_devices}")
            except Exception as e:
                logger.warning(f"Could not detect user devices: {e}")

        # Step 2: Get raw RAG results for quality assessment
        MIN_CHUNK_CONFIDENCE = rag_config["min_chunk_confidence"]
        try:
            logger.info(f"[UNIFIED] Querying knowledge base with top_k=5")
            raw_results = self.researcher.query_knowledge(
                query, top_k=5, session_id=session_id
            )
            logger.info(f"[UNIFIED] Raw RAG results: {len(raw_results)} chunks")
            filtered_results = [
                r for r in raw_results if r.confidence >= MIN_CHUNK_CONFIDENCE
            ]
            logger.info(f"[UNIFIED] Filtered results: {len(filtered_results)} chunks (min_confidence={MIN_CHUNK_CONFIDENCE})")
        except Exception as e:
            filtered_results = []
            logger.error(f"[UNIFIED] RAG search failed: {e}", exc_info=True)

        # Step 3: Assess RAG quality
        rag_quality = self._assess_rag_quality(filtered_results, query)
        logger.info(f"[UNIFIED] RAG quality: is_sufficient={rag_quality.is_sufficient}, avg_confidence={rag_quality.avg_confidence:.2f}, topic_coverage={rag_quality.topic_coverage}")

        # Step 4: Format RAG context from filtered results
        kb_context = None
        if filtered_results:
            kb_context = ""
            for r in filtered_results:
                kb_context += f"---\n{r.quote[:600]}\n\n"
            kb_context = kb_context.strip() if kb_context.strip() else None

        # Step 5: Determine sources and prompt type based on RAG quality
        sources_used = []
        if glooko_available:
            sources_used.append("glooko")

        sources_for_prompt = self._format_sources_for_prompt(
            filtered_results,
            glooko_context,
        )

        if rag_quality.is_sufficient or control_mode:
            # RAG is sufficient - use standard prompt (RAG-only synthesis)
            if kb_context:
                sources_used.append("rag")
            prompt = self._build_prompt(
                query,
                glooko_context,
                kb_context,
                rag_quality.max_confidence,
                sources_for_prompt,
                conversation_history=conversation_history,
                user_devices=user_devices,
                rag_results=filtered_results,
            )
            requires_enhanced_safety = False
        else:
            # RAG is sparse/partial - use hybrid prompt (RAG + parametric)
            if kb_context:
                sources_used.append("rag")
            sources_used.append("parametric")
            prompt = self._build_hybrid_prompt(
                query,
                kb_context,
                rag_quality,
                glooko_context,
                sources_for_prompt,
                conversation_history=conversation_history,
                user_devices=user_devices,
            )
            requires_enhanced_safety = True

        # Step 6: Generate response
        try:
            logger.info(f"[UNIFIED] Generating answer with prompt length: {len(prompt)} chars, rag_mode={not requires_enhanced_safety}")
            answer, llm_info = self._generate_with_fallback(
                prompt=prompt,
                primary_provider=os.environ.get("LLM_PROVIDER", "groq").lower(),
                config=GenerationConfig(temperature=0.3, max_tokens=3000),
            )

            logger.info(f"[UNIFIED] Generated answer length: {len(answer)} chars")
            if len(answer) < 100:
                logger.warning(f"[UNIFIED] SHORT ANSWER: {answer}")

            # Clean up response formatting
            answer = self._clean_response(answer)
            logger.info(f"[UNIFIED] After cleanup: {len(answer)} chars")

            # Step 7a: Verify citations in response
            citation_check = self._verify_citations(answer, query)
            logger.info(f"[CITATION] Response has {citation_check['citation_count']} citations, verified: {citation_check['citation_verified']}")

            # Step 7b: Verify query keyword alignment
            alignment_result = self._verify_query_alignment(query, answer)
            if not alignment_result['aligned']:
                self._log_low_relevancy_response(
                    query=query,
                    response=answer,
                    overlap=alignment_result['overlap'],
                    missing_terms=alignment_result['missing_terms']
                )
            logger.info(f"[RELEVANCY] Keyword overlap: {alignment_result['overlap']:.1%}, aligned: {alignment_result['aligned']}")

            # Step 7c: Calculate knowledge breakdown for UI transparency
            rag_conf = (
                rag_quality.avg_confidence if rag_quality.chunk_count > 0 else 0.0
            )
            parametric_conf = parametric_config[
                "confidence_score"
            ]  # Fixed confidence for parametric knowledge

            # Determine ratios based on prompt type
            if requires_enhanced_safety:
                # Hybrid mode - estimate parametric ratio based on RAG coverage
                parametric_ratio = 0.6 if not kb_context else 0.4
                rag_ratio = 1.0 - parametric_ratio
            else:
                # RAG-only mode
                rag_ratio = 1.0
                parametric_ratio = 0.0

            # Calculate blended confidence
            if rag_ratio + parametric_ratio > 0:
                blended = rag_conf * rag_ratio + parametric_conf * parametric_ratio
            else:
                blended = 0.5

            # Determine primary source type for UI badge
            if glooko_available and "glooko" in sources_used:
                primary_type = "glooko"
            elif parametric_ratio > 0.5:
                primary_type = "parametric"
            elif rag_ratio >= 0.8:
                primary_type = "rag"
            else:
                primary_type = "hybrid"

            knowledge_breakdown = KnowledgeBreakdown(
                rag_confidence=round(rag_conf, 2),
                parametric_confidence=parametric_conf,
                blended_confidence=round(blended, 2),
                rag_ratio=round(rag_ratio, 2),
                parametric_ratio=round(parametric_ratio, 2),
                primary_source_type=primary_type,
            )

            # Determine appropriate disclaimer based on content and sources
            disclaimer = self._get_disclaimer(
                answer, glooko_available, knowledge_breakdown
            )

            # Create response object
            response = UnifiedResponse(
                success=True,
                answer=answer,
                sources_used=sources_used,
                glooko_data_available=glooko_available,
                disclaimer=disclaimer,
                cohort=cohort,
                llm_info=llm_info,
                rag_quality=RAGQualityMetrics(
                    chunk_count=rag_quality.chunk_count,
                    avg_confidence=rag_quality.avg_confidence,
                    sources_covered=rag_quality.sources_covered,
                    topic_coverage=rag_quality.topic_coverage,
                ),
                requires_enhanced_safety_check=requires_enhanced_safety,
                knowledge_breakdown=knowledge_breakdown,
            )

            # Async quality evaluation (non-blocking)
            if self.quality_evaluator and self.config.get('quality_evaluation', {}).get('async', True):
                try:
                    import asyncio
                    # Schedule quality evaluation as background task
                    asyncio.create_task(
                        self._evaluate_quality_async(query, answer, rag_results, rag_quality)
                    )
                except Exception as e:
                    logger.debug(f"Could not schedule async quality evaluation: {e}")

            return response

        except Exception as e:
            error_msg = str(e).lower()
            
            # Check if this is a dosing query with Groq failure
            is_dosing = self._is_dosing_query(query)
            is_groq_error = 'groq' in error_msg or 'empty content' in error_msg
            
            if is_dosing and is_groq_error:
                # Log the safety fallback event
                self._log_safety_fallback(query, f"groq_error: {str(e)[:100]}")
                logger.warning(
                    f"[SAFETY FALLBACK] Dosing query failed with Groq error: {query}"
                )
                
                # Return safe fallback message
                return UnifiedResponse(
                    success=False,
                    answer=self._get_dosing_fallback_message(),
                    sources_used=[],
                    glooko_data_available=glooko_available,
                    cohort=cohort,
                    error_type="safety_fallback",
                    disclaimer="Safety fallback activated - LLM unavailable"
                )
            else:
                # Generic error handling for non-dosing queries
                return UnifiedResponse(
                    success=False,
                    answer=f"Error generating response: {str(e)[:200]}",
                    sources_used=[],
                    glooko_data_available=glooko_available,
                    cohort=cohort,
                )

    async def _evaluate_quality_async(
        self,
        query: str,
        answer: str,
        rag_results: list,
        rag_quality: RAGQualityAssessment
    ):
        """
        Async quality evaluation helper (non-blocking).
        
        Runs quality evaluation in background without blocking response delivery.
        """
        try:
            sources = [r.get('source', 'Unknown') for r in rag_results[:5]]
            rag_quality_dict = {
                'chunk_count': rag_quality.chunk_count,
                'avg_confidence': rag_quality.avg_confidence,
                'sources_covered': rag_quality.sources_covered,
                'topic_coverage': rag_quality.topic_coverage
            }
            
            quality_score = await self.quality_evaluator.evaluate_async(
                query=query,
                response=answer,
                sources=sources,
                rag_quality=rag_quality_dict
            )
            
            logger.debug(
                f"Quality evaluation complete: avg_score={quality_score.average_dimension_score:.2f}"
            )
        except Exception as e:
            logger.error(f"Quality evaluation failed: {e}", exc_info=True)

    def _load_glooko_context(self) -> Optional[str]:
        """Load and format user's Glooko data as context string."""
        try:
            analysis_files = sorted(
                self.analysis_dir.glob("analysis_*.json"), reverse=True
            )
            if not analysis_files:
                return None

            with open(analysis_files[0], "r") as f:
                data = json.load(f)

            metrics = data.get("metrics", {})
            patterns = data.get("patterns", [])
            recommendations = data.get("recommendations", [])
            hourly_analysis = data.get("hourly_analysis", {})

            context = f"""## Your Personal Diabetes Data (from Glooko export)

Analysis Period: {metrics.get('date_range_days', 'unknown')} days
Total Readings: {metrics.get('total_glucose_readings', 0):,}

### Key Metrics
- Average glucose: {metrics.get('average_glucose', 'N/A')} {metrics.get('glucose_unit', 'mg/dL')}
- Standard deviation: {metrics.get('std_deviation', 'N/A')} {metrics.get('glucose_unit', 'mg/dL')}
- Coefficient of variation: {metrics.get('coefficient_of_variation', 'N/A')}%
- Time in range (70-180): {metrics.get('time_in_range_percent', 'N/A')}%
- Time below range (<70): {metrics.get('time_below_range_percent', 'N/A')}%
- Time above range (>180): {metrics.get('time_above_range_percent', 'N/A')}%

### Hourly Breakdown - When Highs Occur (CRITICAL DATA)
"""
            # Add hourly high analysis - this is key for time-specific questions
            highs_data = hourly_analysis.get("highs", {})
            if highs_data.get("peak_time_description"):
                context += (
                    f"**Peak high times: {highs_data.get('peak_time_description')}**\n"
                )
                for evidence in highs_data.get("evidence", [])[:3]:
                    context += f"- {evidence}\n"
            else:
                context += "- Hourly breakdown not available\n"

            context += "\n### Hourly Breakdown - When Lows Occur\n"
            lows_data = hourly_analysis.get("lows", {})
            if lows_data.get("peak_time_description"):
                context += (
                    f"**Peak low times: {lows_data.get('peak_time_description')}**\n"
                )
                for evidence in lows_data.get("evidence", [])[:3]:
                    context += f"- {evidence}\n"
            else:
                context += "- No significant low patterns by hour\n"

            context += "\n### Detected Patterns\n"
            if patterns:
                for p in patterns:
                    context += f"- {p.get('type', 'Unknown')}: {p.get('description', '')} ({p.get('confidence', 0):.0f}% confidence)\n"
            else:
                context += "- No specific patterns detected\n"

            if recommendations:
                context += "\n### Recommendations\n"
                for rec in recommendations:
                    context += f"- {rec}\n"

            return context

        except Exception:
            return None

    def _search_knowledge_base(self, query: str) -> tuple[Optional[str], float]:
        """
        Search knowledge base and format results as context string with explicit source metadata.

        Returns:
            Tuple of (context_string, max_confidence) where max_confidence is the highest
            confidence score among retrieved chunks (0.0 if no results).
        """
        try:
            # Use the new query_knowledge method for documentation collections
            results = self.researcher.query_knowledge(query, top_k=5)

            if not results:
                return None, 0.0

            # Filter out low confidence results (< 0.35)
            # Results below this threshold are often noise/off-topic
            MIN_CHUNK_CONFIDENCE = self.config["rag_quality"]["min_chunk_confidence"]
            filtered_results = [
                r for r in results if r.confidence >= MIN_CHUNK_CONFIDENCE
            ]

            if not filtered_results:
                return None, 0.0

            # Calculate max confidence for response calibration
            max_confidence = max(r.confidence for r in filtered_results)

            # Format results as simple text blocks (NO metadata that could leak into response)
            context = ""
            for i, r in enumerate(filtered_results, 1):
                # Just the content, no technical metadata
                context += f"---\n{r.quote[:600]}\n\n"

            if not context.strip():
                return None, 0.0

            return context.strip(), max_confidence

        except Exception:
            return None, 0.0

    def _assess_rag_quality(self, results: list, query: str) -> RAGQualityAssessment:
        """
        Assess quality of RAG retrieval to determine if hybrid augmentation needed.

        Criteria for 'sufficient' coverage:
        - ≥3 chunks retrieved
        - Average confidence ≥0.7
        - At least 2 unique sources (for corroboration)

        Criteria for 'partial' coverage:
        - 1-2 chunks OR avg confidence 0.5-0.7
        - Some relevant information but gaps likely

        Criteria for 'sparse' coverage:
        - 0 chunks OR avg confidence <0.5
        - Needs parametric augmentation
        """
        if not results:
            return RAGQualityAssessment(
                chunk_count=0,
                avg_confidence=0.0,
                max_confidence=0.0,
                min_confidence=0.0,
                sources_covered=[],
                source_diversity=0,
                topic_coverage="sparse",
            )

        # Calculate metrics
        chunk_count = len(results)
        confidences = [r.confidence for r in results]
        avg_confidence = sum(confidences) / len(confidences)
        max_confidence = max(confidences)
        min_confidence = min(confidences)

        # Get unique sources
        sources_covered = list(set(r.source for r in results))
        source_diversity = len(sources_covered)

        # Determine topic coverage
        min_chunks = self.config["rag_quality"]["min_chunks"]
        min_confidence = self.config["rag_quality"]["min_confidence"]
        min_sources = self.config["rag_quality"]["min_sources"]

        if (
            chunk_count >= min_chunks
            and avg_confidence >= min_confidence
            and source_diversity >= min_sources
        ):
            topic_coverage = "sufficient"
        elif chunk_count >= 1 and avg_confidence >= 0.5:
            topic_coverage = "partial"
        else:
            topic_coverage = "sparse"

        assessment = RAGQualityAssessment(
            chunk_count=chunk_count,
            avg_confidence=avg_confidence,
            max_confidence=max_confidence,
            min_confidence=min_confidence,
            sources_covered=sources_covered,
            source_diversity=source_diversity,
            topic_coverage=topic_coverage,
        )

        # Log assessment for debugging retrieval issues
        logger.debug(
            f"RAG quality assessment: chunks={assessment.chunk_count}, "
            f"avg_confidence={assessment.avg_confidence:.2f}, "
            f"coverage={assessment.topic_coverage}, "
            f"sources={assessment.sources_covered}"
        )

        return assessment

    def _format_sources_for_citation(
        self,
        results: list,
    ) -> str:
        """Format sources with numbered references for easy citation.
        
        Creates a section that LLM can easily reference in response.
        Example output:
        === RETRIEVED SOURCES (CITE BY NUMBER [1], [2], etc.) ===
        [1] OpenAPS Documentation - Autosens Algorithm
        [2] ADA Standards of Care 2026
        === END SOURCES ===
        """
        if not results:
            return ""
        
        source_section = "\n=== RETRIEVED SOURCES (CITE BY NUMBER [1], [2], etc.) ===\n"
        
        sources_seen = set()
        source_num = 1
        for r in results:
            source_name = getattr(r, "source", "Unknown Source")
            if source_name not in sources_seen:
                sources_seen.add(source_name)
                source_section += f"[{source_num}] {source_name}\n"
                source_num += 1
        
        source_section += "=== END SOURCES ===\n"
        return source_section

    def _format_sources_for_prompt(
        self,
        results: list,
        glooko_context: Optional[str],
    ) -> str:
        """Format available sources for citation in prompts."""
        source_conf: dict[str, float] = {}
        for r in results or []:
            if not getattr(r, "source", None):
                continue
            existing = source_conf.get(r.source, 0.0)
            source_conf[r.source] = max(existing, float(r.confidence or 0.0))

        lines = []
        for source, conf in sorted(source_conf.items()):
            lines.append(f"- {source} (confidence: {conf:.2f})")

        if glooko_context:
            lines.append("- Glooko data (confidence: 1.00)")

        if not lines:
            lines.append("- General knowledge (confidence: 0.50)")

        return "SOURCES AVAILABLE (cite using [source_name, confidence: X.X]):\n" + "\n".join(lines)

    def _build_hybrid_prompt(
        self,
        query: str,
        rag_context: Optional[str],
        rag_quality: RAGQualityAssessment,
        glooko_context: Optional[str] = None,
        sources_for_prompt: str = "",
        conversation_history: Optional[list] = None,
        user_devices: Optional[List[str]] = None,
    ) -> str:
        """
        Build prompt that combines RAG chunks with parametric knowledge instruction.

        Creates a natural, conversational response in flowing paragraphs
        without numbered sections or inline citations.

        Only called when RAG coverage is partial/sparse.

        Args:
            query: User's question
            rag_context: Formatted RAG context
            rag_quality: RAG quality assessment
            glooko_context: Optional Glooko data context
            conversation_history: List of previous exchanges for context
            user_devices: List of user device names for device-aware prompting
        """
        if conversation_history is None:
            conversation_history = []

        # Build device-aware preamble with clean device name
        device_preamble = ""
        primary_device = user_devices[0] if user_devices and len(user_devices) > 0 else None

        if primary_device:
            device_preamble = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 CRITICAL DEVICE CONTEXT - READ THIS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The user is using: **{primary_device}**

YOUR PRIMARY JOB: Explain how THEIR {primary_device} solves this problem.

MANDATORY RESPONSE STRUCTURE:
1. LEAD with {primary_device} features (first 2-3 sentences)
2. Reference device-specific capabilities by their EXACT names from the manual
3. Use possessive language: "Your {primary_device}..." NOT "Some systems..." or "Pumps can..."

FORBIDDEN PHRASES (will fail this task):
❌ "your pump" or "your system" (too generic)
❌ "insulin delivery systems" or "closed-loop technology" (too academic)
❌ "Consider adjusting basal rates" (manual pump advice, not hybrid closed-loop)
❌ "Some devices have..." (implies you don't know THEIR device)

REQUIRED PHRASES (use these):
✅ "Your {primary_device} has a feature called..."
✅ "Use {primary_device}'s [specific feature name] to..."
✅ "In your {primary_device} settings, you can..."
✅ "Your {primary_device} system handles this by..."

KNOWLEDGE SOURCE PRIORITY:
1️⃣ User's {primary_device} manual (RETRIEVED KNOWLEDGE below) - ALWAYS cite first
2️⃣ Their personal data patterns
3️⃣ Clinical guidelines (only if directly relevant to their device usage)

If you don't have {primary_device}-specific information in the retrieved context,
say: "Check your {primary_device} manual for [specific feature]" - NEVER give generic pump advice.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        else:
            device_preamble = """
Note: The user has not uploaded device-specific documentation. Provide general guidance
and recommend they consult their specific device manual for detailed instructions.
"""

        # Format conversation history for prompt inclusion
        history_section = ""
        if conversation_history:
            history_parts = []
            for exchange in conversation_history[-5:]:  # Last 5 exchanges max
                q = exchange.get("query", "")
                r = exchange.get("response", "")
                # Truncate long responses
                if len(r) > 400:
                    r = r[:400] + "..."
                history_parts.append(f"User: {q}")
                history_parts.append(f"Assistant: {r}")
            history_section = "\n".join(history_parts)

        history_prompt = ""
        if history_section:
            history_prompt = f"""
CONVERSATION HISTORY (reference previous questions if relevant, build on earlier advice, avoid repeating information already provided):
{history_section}
---END HISTORY---

"""

        # Build context section
        context_section = ""
        sources_cited = ""
        if rag_context:
            # Note: rag_results not available in hybrid mode, so we format sources from context
            context_section = f"""
RETRIEVED KNOWLEDGE:
{rag_context}
"""

        data_keywords = [
            "my",
            "glucose",
            "sugar",
            "reading",
            "average",
            "pattern",
            "data",
            "level",
            "a1c",
            "time in range",
            "tir",
        ]
        query_lower = query.lower()
        is_data_question = any(kw in query_lower for kw in data_keywords)

        if glooko_context and is_data_question:
            context_section += f"""
USER'S PERSONAL DIABETES DATA:
{glooko_context}
"""
        if sources_for_prompt:
            context_section += f"""

{sources_for_prompt}
"""

        prompt = f"""You are Diabetes Buddy, a friendly AI assistant helping people with Type 1 diabetes.
{device_preamble}
{history_prompt}
{sources_cited}
{context_section}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER'S SPECIFIC QUESTION: "{query}"

YOUR RESPONSE REQUIREMENTS:
1. Directly answer the EXACT question asked above
2. Use key terms from the query in your response
3. Address the specific scenario described
4. Start with a direct answer, then provide supporting details
5. Do NOT provide generic background unless it directly supports the answer

If the query is too vague to answer specifically, ask clarifying questions.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CITATION REQUIREMENTS (MANDATORY):
- Cite EVERY factual claim with source attribution [e.g., [1], [2] for knowledge, [Glooko] for data]
- Minimum 3 citations required per response (reference sources by number or [Glooko])
- Do NOT make claims about devices, settings, dosages, or physiology without attribution
- If insufficient sources available, state limitations explicitly

GOOD RESPONSE EXAMPLE:
Query: "Why does my algorithm keep suspending insulin?"
Response: "Your system suspends insulin when it predicts low blood sugar [1]. The automatic suspension feature [1] triggers when glucose is projected to drop below your threshold [2]..."

BAD RESPONSE EXAMPLE (too generic):
Query: "Why does my algorithm keep suspending insulin?"
Response: "Closed-loop systems use algorithms to manage insulin delivery. These systems are designed to prevent hypoglycemia..."

Your response should follow the GOOD example pattern - answer the specific question directly.

RESPONSE FORMAT - Write 2-3 natural, conversational paragraphs:

Paragraph 1: Acknowledge the user's question. If (and only if) they asked about their data, reference specific times and patterns with citations [Glooko].

Paragraph 2: Provide 2-4 actionable strategies with citations [e.g., [1]]. If they have a device like {primary_device or 'a closed-loop system'}, mention its specific features by name with source citations. Include specific numbers, timings, or percentage ranges with citations.

Paragraph 3: Brief closing that MUST include "check with your healthcare team" [e.g., [2]] or "consult your healthcare provider" [e.g., [2]] for personalized adjustments.

CRITICAL RULES:
- NEVER calculate specific insulin doses without source attribution
- DO provide evidence-based ranges with citations ("guidelines suggest 70-180 mg/dL target [1]")
- Only mention personal data if the question is about their data [Glooko]
- DO include specific instructions from device manual ONLY if cited [e.g., [1]]
- MUST include actionable words like "try", "consider", "adjust", "monitor" with citations [e.g., [2]]
- MUST end with guidance to consult healthcare team with source [e.g., [2]]
- Use paragraph breaks with \n\n (blank lines) between paragraphs for readability
- NO numbered lists, NO section headings, NO bullet points
- Reference sources by number [1], [2], [3] or [Glooko] throughout
- Sound warm and supportive, like a knowledgeable friend teaching someone
- If the user has a device, use its EXACT name and feature names with citations
- If the retrieved knowledge does not include the requested device feature, say so [Source limitation]

REMEMBER: Users need to verify information. Cite your sources throughout using [1], [2], [Glooko], etc.

Write your response now - natural paragraphs with citations:
"""
        return prompt

    def _build_prompt(
        self,
        query: str,
        glooko_context: Optional[str],
        kb_context: Optional[str],
        kb_confidence: float = 0.0,
        sources_for_prompt: str = "",
        conversation_history: Optional[list] = None,
        user_devices: Optional[List[str]] = None,
        rag_results: Optional[list] = None,
    ) -> str:
        """
        Build a natural, conversational prompt for the LLM.

        Creates friendly, synthesized responses in flowing paragraphs
        with mandatory citation requirements for factual claims.

        Args:
            query: User's question
            glooko_context: Formatted Glooko data context
            kb_context: Formatted knowledge base context
            kb_confidence: Maximum confidence score from KB results (0.0-1.0)
            conversation_history: List of previous exchanges for context
            user_devices: List of user device names for device-aware prompting
            rag_results: Raw RAG results for citation formatting
        """
        if conversation_history is None:
            conversation_history = []

        # Build device-aware preamble with clean device name
        device_preamble = ""
        primary_device = user_devices[0] if user_devices and len(user_devices) > 0 else None

        if primary_device:
            device_preamble = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 CRITICAL DEVICE CONTEXT - READ THIS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The user is using: **{primary_device}**

YOUR PRIMARY JOB: Explain how THEIR {primary_device} solves this problem.

MANDATORY RESPONSE STRUCTURE:
1. LEAD with {primary_device} features (first 2-3 sentences)
2. Reference device-specific capabilities by their EXACT names from the manual
3. Use possessive language: "Your {primary_device}..." NOT "Some systems..." or "Pumps can..."

FORBIDDEN PHRASES (will fail this task):
❌ "your pump" or "your system" (too generic)
❌ "insulin delivery systems" or "closed-loop technology" (too academic)
❌ "Consider adjusting basal rates" (manual pump advice, not hybrid closed-loop)
❌ "Some devices have..." (implies you don't know THEIR device)

REQUIRED PHRASES (use these):
✅ "Your {primary_device} has a feature called..."
✅ "Use {primary_device}'s [specific feature name] to..."
✅ "In your {primary_device} settings, you can..."
✅ "Your {primary_device} system handles this by..."

KNOWLEDGE SOURCE PRIORITY:
1️⃣ User's {primary_device} manual (RETRIEVED INFORMATION below) - ALWAYS cite first
2️⃣ Their personal data patterns
3️⃣ Clinical guidelines (only if directly relevant to their device usage)

If you don't have {primary_device}-specific information in the retrieved context,
say: "Check your {primary_device} manual for [specific feature]" - NEVER give generic pump advice.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        else:
            device_preamble = """
Note: The user has not uploaded device-specific documentation. Provide general guidance
and recommend they consult their specific device manual for detailed instructions.
"""

        # Format conversation history for prompt inclusion
        history_section = ""
        if conversation_history:
            history_parts = []
            for exchange in conversation_history[-5:]:  # Last 5 exchanges max
                q = exchange.get("query", "")
                r = exchange.get("response", "")
                # Truncate long responses
                if len(r) > 400:
                    r = r[:400] + "..."
                history_parts.append(f"User: {q}")
                history_parts.append(f"Assistant: {r}")
            history_section = "\n".join(history_parts)
        has_kb_results = kb_context is not None
        has_glooko = glooko_context is not None

        # Determine if this is a data question early (used in multiple places below)
        data_keywords = [
            "my",
            "glucose",
            "sugar",
            "reading",
            "average",
            "pattern",
            "data",
            "level",
            "a1c",
            "time in range",
            "tir",
        ]
        query_lower = query.lower()
        is_data_question = any(kw in query_lower for kw in data_keywords)

        # Build context section
        context_parts = []
        if kb_context:
            context_parts.append(f"RETRIEVED INFORMATION:\n{kb_context}")
        if glooko_context and is_data_question:
            context_parts.append(f"USER'S DIABETES DATA:\n{glooko_context}")
        if sources_for_prompt:
            context_parts.append(sources_for_prompt)

        context = "\n\n".join(context_parts) if context_parts else ""

        # Build conversation history section for prompt
        history_prompt = ""
        if history_section:
            history_prompt = f"""
CONVERSATION HISTORY (reference previous questions if relevant, build on earlier advice, avoid repeating information already provided):
{history_section}
---END HISTORY---

"""

        # Format sources for citation
        sources_cited = self._format_sources_for_citation(rag_results or [])
        
        # Determine response approach based on what we have
        if has_kb_results:
            return f"""You are Diabetes Buddy, a friendly AI assistant helping people with Type 1 diabetes.
{device_preamble}
{history_prompt}
{sources_cited}
KNOWLEDGE BASE CONTENT:
{context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER'S SPECIFIC QUESTION: "{query}"

YOUR RESPONSE REQUIREMENTS:
1. Directly answer the EXACT question asked above
2. Use key terms from the query in your response
3. Address the specific scenario described
4. Start with a direct answer, then provide supporting details
5. Do NOT provide generic background unless it directly supports the answer

If the query is too vague to answer specifically, ask clarifying questions.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CITATION REQUIREMENTS (MANDATORY):
- Cite EVERY factual claim with source attribution using format: [Source Number]
- Minimum 3 citations required per response (reference numbers from sources list above)
- For device-specific claims: cite the device manual [e.g., [1]]
- For clinical claims: cite clinical sources or guidelines [e.g., [2]]
- Do NOT make claims about devices, settings, dosages, or physiology without attribution
- If insufficient sources available, state limitations explicitly

GOOD RESPONSE EXAMPLE:
Query: "How do I change my basal rate on my pump?"
Response: "To change your basal rate on your pump, follow these steps: 1) Navigate to Settings menu [1], 2) Select Basal Rates [1]..."

BAD RESPONSE EXAMPLE (too generic):
Query: "How do I change my basal rate on my pump?"
Response: "Basal insulin is an important component of diabetes management. It provides background insulin throughout the day..."

Your response should follow the GOOD example pattern - answer the specific question directly.

RESPONSE FORMAT - Write 2-3 natural, conversational paragraphs:

Paragraph 1: Acknowledge the user's question. If (and only if) they asked about their data, connect it to their Glooko patterns. Otherwise, do not mention personal data.

Paragraph 2: Provide 2-4 actionable strategies using their specific device features with citations. When explaining device features:
   - Include HOW to use them with source citations [e.g., [1]]
   - Explain WHEN to use them with supporting evidence [e.g., [2]]
   - Include specific numbers ONLY if they appear explicitly in the retrieved knowledge [e.g., [1]]
   - Make it actionable enough that the user could follow the steps

Paragraph 3: Brief closing that MUST include "check with your healthcare team" [e.g., [2]] or "consult your healthcare provider" for personalized adjustments.

CRITICAL RULES:
- NEVER calculate specific insulin doses without source attribution
- DO provide evidence-based ranges with citations ("guidelines suggest 70-180 mg/dL target [1]")
- Only mention personal data if the question is about their data
- DO include specific instructions from device manual ONLY if cited from retrieved knowledge [e.g., [1]]
- MUST include actionable words like "try", "consider", "adjust", "monitor" with citations [e.g., [2]]
- MUST end with guidance to consult their healthcare team/provider/doctor with source reference [e.g., [3]]
- Use paragraph breaks with \n\n (blank lines) between paragraphs for readability
- NO numbered lists, NO section headings, NO bullet points in response body
- Reference sources by number: [1], [2], [3], etc. throughout response
- Sound warm and supportive, like a knowledgeable friend teaching someone
- If the user has a device, use its EXACT name and feature names throughout with citations
- If the retrieved knowledge does not include the requested device feature, say so and suggest checking the manual

REMEMBER: Users need to verify information. Cite your sources throughout the response using [1], [2], etc.

Write your response now - natural paragraphs with citations, no structured format:
"""

        elif has_glooko:

            if is_data_question:
                return f"""You are Diabetes Buddy, a friendly AI assistant helping people with Type 1 diabetes.
{device_preamble}
{history_prompt}
{sources_cited}
USER'S DIABETES DATA:
{context}

USER QUESTION: {query}

CITATION REQUIREMENTS (MANDATORY):
- Cite EVERY claim with source attribution: [Glooko] for personal data, [Source Number] for knowledge base
- Minimum 3 citations required per response
- For data analysis: cite [Glooko] when referencing personal patterns
- For clinical strategies: cite sources [1], [2], etc.

RESPONSE FORMAT - Write 2-3 natural, conversational paragraphs:

Paragraph 1: Acknowledge what the user is experiencing and reference specific patterns/times from their data [Glooko].

Paragraph 2: Provide 2-4 actionable strategies with citations. Include specific numbers, timings, or percentage ranges [Glooko]. If they have a device, mention its specific features [1].

Paragraph 3: Brief closing that MUST include "check with your healthcare team" [2] or "consult your healthcare provider" for personalized adjustments.

CRITICAL RULES:
- NEVER calculate specific insulin doses without source attribution
- DO use specific times/percentages from their data with citations [Glooko]
- MUST include actionable words like "try", "consider", "adjust", "monitor" with citations [1], [2]
- MUST end with guidance to consult their healthcare team/provider [2]
- Use paragraph breaks with \n\n (blank lines) between paragraphs
- NO numbered lists, NO section headings, NO bullet points
- Reference sources throughout: [Glooko] or [1], [2], [3], etc.
- Sound warm and conversational

REMEMBER: Cite your sources to help users verify information: [Glooko] or [1], [2], [3].

Write your response now with citations:
"""
            else:
                # Off-topic question - redirect without dumping data
                return f"""Someone asked: "{query}"

This is off-topic (not about diabetes). Say ONLY this:

"I'm focused on diabetes-related questions. Is there anything about your glucose levels or diabetes management I can help with?"

Output that exact sentence and nothing else."""

        else:
            # No relevant information available
            return f"""You are a friendly diabetes assistant. Someone asked: "{query}"
{history_prompt}
You don't have specific information about this topic in your knowledge base.

If it's completely off-topic (not about diabetes at all), respond with:
"I'm focused on diabetes-related questions. Is there anything about your glucose levels, device management, or diabetes care I can help with?"

If it IS about diabetes but you don't have information, respond with something like:
"I don't have specific information about that in my knowledge base. For detailed guidance, I'd recommend checking with your healthcare team or your device manual."

Keep it to 1-2 sentences. Be friendly and supportive."""

    def _get_disclaimer(
        self,
        answer: str,
        glooko_available: bool,
        knowledge_breakdown: Optional[KnowledgeBreakdown] = None,
    ) -> str:
        """Generate appropriate disclaimer based on response content and source mix."""
        # Skip if already has healthcare mention
        if "healthcare" in answer.lower() or "doctor" in answer.lower():
            base = ""
        elif glooko_available:
            base = "This analysis includes your personal data. Discuss any changes with your healthcare team."
        else:
            base = "This is educational information. Always consult your healthcare provider."

        # Add parametric-specific warning if heavy parametric use
        max_parametric_ratio = self.config["parametric_usage"]["max_ratio"]
        if (
            knowledge_breakdown
            and knowledge_breakdown.parametric_ratio > max_parametric_ratio
        ):
            parametric_warning = "\n\n⚠️ This answer includes general diabetes knowledge. For device-specific procedures, consult your device manual or healthcare provider."
            return base + parametric_warning if base else parametric_warning

        return base

    def _verify_citations(self, response: str, query: str, min_citations: int = 1) -> dict:
        """
        Verify citation count in response and log if insufficient.
        
        Detects multiple citation formats:
        - Numbered: [1], [2], [3]
        - Source-based: [Source Name], [Manual Title], etc.
        - Data-based: [Glooko], [Glooko Data]
        
        Args:
            response: Generated response text
            query: Original user query
            min_citations: Minimum required citations for adequate coverage (default: 1, very permissive)
            
        Returns:
            Dict with citation_count, citation_verified flag, and list of citations found
        """
        # Find citations in multiple formats:
        # [1], [2], [Source Name], [Manual Title], [Glooko], etc.
        citation_pattern = r'\[[^\]]+\]'
        citations = re.findall(citation_pattern, response)
        citation_count = len(citations)
        
        # Determine if response length requires minimum citations
        response_length = len(response)
        # Very permissive: only flag if response is substantial AND has zero citations
        # Groq's response quality is good even without explicit inline citations
        requires_citations = response_length > 500 and citation_count == 0
        
        citation_verified = True
        if requires_citations:
            citation_verified = False
            # Log low-citation response (informational only, not a blocking issue)
            logger.info(
                f"[CITATION] Response has no citations despite length {citation_count} "
                f"(query: {query[:60]}...)"
            )
        
        return {
            "citation_count": citation_count,
            "citation_verified": citation_verified,
            "citations_found": citations,
            "response_length": response_length
        }

    def _log_low_citation_response(self, query: str, response: str, citation_count: int) -> None:
        """Log low-citation responses to CSV for analysis."""
        try:
            csv_path = self.project_root / "data" / "low_citation_responses.csv"
            import csv
            from datetime import datetime
            
            # Ensure directory exists
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists to determine if we need header
            file_exists = csv_path.exists()
            
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'query', 'citation_count', 
                        'response_length', 'response_preview'
                    ])
                
                response_preview = response[:200].replace('\n', ' ')
                writer.writerow([
                    datetime.now().isoformat(),
                    query[:100],
                    citation_count,
                    len(response),
                    response_preview
                ])
            
            logger.debug(f"[CITATION] Logged low-citation response to {csv_path}")
        except Exception as e:
            logger.warning(f"Failed to log low-citation response: {e}")

    def _verify_query_alignment(self, query: str, response: str, min_overlap: float = 0.4) -> dict:
        """
        Verify query keyword alignment in response.
        
        Extracts key terms from query and checks if response addresses them.
        
        Args:
            query: Original user query
            response: Generated response text
            min_overlap: Minimum keyword overlap percentage (0.0-1.0)
            
        Returns:
            Dict with aligned flag, overlap percentage, and missing_terms list
        """
        # Common stopwords to filter out
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "how", "what", "when", "where", "why", "who", "which", "do", "does", 
            "did", "can", "could", "should", "would", "will", "i", "my", "me",
            "in", "on", "at", "to", "from", "by", "with", "about", "for", "of"
        }
        
        # Extract key terms from query (2+ characters, not stopwords)
        query_lower = query.lower()
        query_words = re.findall(r'\b[a-z]{2,}\b', query_lower)
        key_terms = [w for w in query_words if w not in stopwords]
        
        if not key_terms:
            # No key terms to check
            return {
                "aligned": True,
                "overlap": 1.0,
                "missing_terms": []
            }
        
        # Check which key terms appear in response (case-insensitive)
        response_lower = response.lower()
        matched_terms = [term for term in key_terms if term in response_lower]
        missing_terms = [term for term in key_terms if term not in response_lower]
        
        # Calculate overlap percentage
        overlap = len(matched_terms) / len(key_terms) if key_terms else 1.0
        aligned = overlap >= min_overlap
        
        if not aligned:
            logger.warning(
                f"[RELEVANCY] Low keyword overlap: {overlap:.2%} ({len(matched_terms)}/{len(key_terms)} terms) "
                f"Missing: {missing_terms[:5]}"
            )
        
        return {
            "aligned": aligned,
            "overlap": round(overlap, 3),
            "missing_terms": missing_terms[:5],  # Limit to first 5
            "matched_terms": matched_terms,
            "total_key_terms": len(key_terms)
        }

    def _log_low_relevancy_response(
        self, 
        query: str, 
        response: str, 
        overlap: float, 
        missing_terms: List[str]
    ) -> None:
        """Log low-relevancy responses to CSV for analysis."""
        try:
            csv_path = self.project_root / "data" / "low_relevancy_responses.csv"
            import csv
            from datetime import datetime
            
            # Ensure directory exists
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists to determine if we need header
            file_exists = csv_path.exists()
            
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'query', 'overlap_percentage', 
                        'missing_terms', 'response_preview'
                    ])
                
                response_preview = response[:200].replace('\n', ' ')
                missing_str = ", ".join(missing_terms)
                writer.writerow([
                    datetime.now().isoformat(),
                    query[:100],
                    f"{overlap:.1%}",
                    missing_str,
                    response_preview
                ])
            
            logger.debug(f"[RELEVANCY] Logged low-relevancy response to {csv_path}")
        except Exception as e:
            logger.warning(f"Failed to log low-relevancy response: {e}")

    def _clean_response(self, response: str) -> str:
        """Clean and format LLM response for conversational readability."""
        import re

        # Remove any citation patterns that slipped through
        # Patterns like (ADA Standards of Care), (clinical research), [Source: X], etc.
        citation_patterns = [
            r"\s*\([^)]*(?:documentation|standards|guidelines|research|education|data|Wikipedia|ADA|NICE|Glooko)[^)]*\)",
            r"\s*\[Source:[^\]]*\]",
            r"\s*\[General medical knowledge\]",
        ]
        for pattern in citation_patterns:
            response = re.sub(pattern, "", response, flags=re.IGNORECASE)

        # Remove structured format headers if LLM used them anyway
        structured_headers = [
            r"^\s*\d+\.\s*ACKNOWLEDGE:?\s*",
            r"^\s*\d+\.\s*EVIDENCE-BASED STRATEGIES:?\s*",
            r"^\s*\d+\.\s*SAFETY BOUNDARY:?\s*",
            r"^\s*\d+\.\s*HEALTHCARE DISCUSSION STARTER:?\s*",
            r"^\s*\d\)\s*Strategy:\s*",
        ]
        lines = response.split('\n')
        cleaned_lines = []
        for line in lines:
            cleaned_line = line
            for pattern in structured_headers:
                cleaned_line = re.sub(pattern, "", cleaned_line, flags=re.MULTILINE | re.IGNORECASE)
            # Only keep non-empty lines or preserve intentional blank lines
            if cleaned_line.strip() or (not line.strip() and cleaned_lines and cleaned_lines[-1].strip()):
                cleaned_lines.append(cleaned_line)
        response = '\n'.join(cleaned_lines)

        # Fix common sentence fragments from chunk boundaries
        response = re.sub(
            r"\.\s+of this,", ". Because of this,", response, flags=re.IGNORECASE
        )
        response = re.sub(r"\.,\s+being", ". Being", response)
        response = re.sub(r"\.\s+and\s+continue", ", and continue", response)

        # Fix orphaned sentence starts (lowercase after period)
        response = re.sub(
            r"\.\s+([a-z])", lambda m: ". " + m.group(1).upper(), response
        )

        # Remove double periods and clean up spacing
        response = response.replace("..", ".")
        response = re.sub(r"\s{3,}", "  ", response)  # Normalize multiple spaces

        # Ensure proper paragraph spacing (normalize to double newlines)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", response) if p.strip()]
        response = "\n\n".join(paragraphs)

        # Remove any trailing metadata or source sections
        # These might be added by the LLM despite instructions
        response = re.sub(r"\n*###?\s*Sources?\s*\n.*$", "", response, flags=re.DOTALL | re.IGNORECASE)
        response = re.sub(r"\n*\*\*Sources?\*\*:?\s*\n.*$", "", response, flags=re.DOTALL | re.IGNORECASE)

        return response.strip()
