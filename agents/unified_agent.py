"""
Unified Agent for Diabetes Buddy

Single agent that handles all queries without routing.
Every query gets both user's Glooko data and knowledge base results.
The LLM decides what's relevant.
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import re

from .llm_provider import LLMFactory, GenerationConfig

# Import researcher for knowledge base search
try:
    from .researcher_chromadb import ResearcherAgent
    CHROMADB_AVAILABLE = True
except ImportError:
    from .researcher import ResearcherAgent
    CHROMADB_AVAILABLE = False


@dataclass
class UnifiedResponse:
    """Response from the unified agent."""
    success: bool
    answer: str
    sources_used: list[str]  # Which sources contributed: "glooko", "knowledge_base", etc.
    glooko_data_available: bool
    disclaimer: str = ""


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
        r'\bhow much insulin\b',
        r'\binsulin dose\b',
        r'\bbolus calculation\b',
        r'\bcalculate.*bolus\b',
        r'\bcarb ratio\b',
        r'\binsulin.*carb.*ratio\b',
        r'\bcalculate.*insulin\b',
        r'\bdose.*carbs?\b',
        r'\binsulin.*for.*carbs?\b',
    ]

    PRODUCT_CONFIG_PATTERNS = [
        r'\b(configure|setup|install|set up)\s+(autosens|autotune|extended bolus|temp basal|basal rate|carb ratio|correction factor|sensitivity factor)\b',
        r'\bhow.*(configure|setup|install|set up).*(pump|cgm|sensor|loop|openaps|androidaps|camaps|control.?iq|omnipod|tandem|medtronic)\b',
        r'\b(configure|setup|install|set up).*(pump|cgm|sensor|loop|openaps|androidaps|camaps|control.?iq|omnipod|tandem|medtronic)\b',
    ]

    def __init__(self, project_root: Optional[str] = None):
        self.llm = LLMFactory.get_provider()

        if project_root is None:
            project_root = Path(__file__).parent.parent
        else:
            project_root = Path(project_root)

        self.project_root = project_root
        self.analysis_dir = project_root / "data" / "analysis"

        # Initialize knowledge base researcher
        self.researcher = ResearcherAgent(project_root=project_root)

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

    def process(self, query: str) -> UnifiedResponse:
        """
        Process any query with full context - no routing needed.

        Args:
            query: User's question (any type)

        Returns:
            UnifiedResponse with answer and metadata
        """
        # Check for dangerous queries first
        if self._detect_dosing_query(query):
            return UnifiedResponse(
                success=True,
                answer="I cannot provide specific insulin dosing advice. Individual insulin-to-carbohydrate ratios vary. Please consult your diabetes care team.\n\n### Sources\n- Safety guidelines",
                sources_used=[],
                glooko_data_available=False,
                disclaimer="This is a safety response for dosing questions.",
            )

        if self._detect_product_config_query(query):
            return UnifiedResponse(
                success=True,
                answer="I can provide general diabetes management principles, but cannot give device-specific configuration instructions. Please refer to your device's user manual or contact your healthcare provider.\n\n### Sources\n- Educational resources",
                sources_used=[],
                glooko_data_available=False,
                disclaimer="This is a safety response for product configuration questions.",
            )

        sources_used = []

        # Step 1: Load user's Glooko data (always try)
        glooko_context = self._load_glooko_context()
        glooko_available = glooko_context is not None
        if glooko_available:
            sources_used.append("glooko")

        # Step 2: Search knowledge base (always search)
        kb_context = self._search_knowledge_base(query)
        if kb_context:
            sources_used.append("knowledge_base")

        # Step 3: Build unified prompt with all context
        prompt = self._build_prompt(query, glooko_context, kb_context)

        # Step 4: Generate response
        try:
            answer = self.llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.7),
            )

            # Determine appropriate disclaimer based on content
            disclaimer = self._get_disclaimer(answer, glooko_available)

            return UnifiedResponse(
                success=True,
                answer=answer,
                sources_used=sources_used,
                glooko_data_available=glooko_available,
                disclaimer=disclaimer,
            )

        except Exception as e:
            return UnifiedResponse(
                success=False,
                answer=f"Error generating response: {str(e)[:200]}",
                sources_used=[],
                glooko_data_available=glooko_available,
            )

    def _load_glooko_context(self) -> Optional[str]:
        """Load and format user's Glooko data as context string."""
        try:
            analysis_files = sorted(self.analysis_dir.glob("analysis_*.json"), reverse=True)
            if not analysis_files:
                return None

            with open(analysis_files[0], 'r') as f:
                data = json.load(f)

            metrics = data.get("metrics", {})
            patterns = data.get("patterns", [])
            recommendations = data.get("recommendations", [])

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

### Detected Patterns
"""
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

    def _search_knowledge_base(self, query: str) -> Optional[str]:
        """Search knowledge base and format results as context string with explicit source metadata."""
        try:
            # Use the new query_knowledge method for documentation collections
            results = self.researcher.query_knowledge(query, top_k=5)

            if not results:
                return None

            # Format results with explicit chunk numbering and source metadata
            context = "## Knowledge Base Results\n\n"
            context += "The following chunks were retrieved from the knowledge base. "
            context += "Use ONLY these chunks to answer questions about diabetes management.\n\n"

            chunk_num = 1
            for r in results:
                # Get collection name from source (e.g., "openaps_docs", "loop_docs")
                collection = getattr(r, 'collection', r.source) if hasattr(r, 'collection') else r.source
                confidence = r.confidence

                # Format each chunk with clear metadata
                context += f"[Chunk {chunk_num} | source: {collection} | confidence: {confidence:.2f}]\n"
                context += f"{r.quote[:500]}\n\n"
                chunk_num += 1

            if chunk_num == 1:
                return None  # No chunks were added

            return context

        except Exception:
            return None

    def _build_prompt(self, query: str, glooko_context: Optional[str], kb_context: Optional[str]) -> str:
        """Build the unified prompt with all available context and strict citation requirements."""

        prompt_parts = []

        # Add available context
        if glooko_context:
            prompt_parts.append(glooko_context)

        if kb_context:
            prompt_parts.append(kb_context)

        has_kb_results = kb_context is not None
        has_glooko = glooko_context is not None

        if not prompt_parts:
            prompt_parts.append("(No personal data or knowledge base results available)")

        context = "\n\n".join(prompt_parts)

        # Build instructions based on what context is available
        if has_kb_results:
            kb_instructions = """
## CRITICAL: Knowledge Base Citation Requirements
- For ANY claim about diabetes management, devices, or techniques: Use ONLY the Knowledge Base Results above
- DO NOT reference books, papers, or sources not present in the retrieved chunks
- DO NOT hallucinate or invent references (e.g., "Think Like a Pancreas" unless it appears in the chunks)
- DO NOT mention specific product names or tools (e.g., avoid "Nightscout", "OpenAPS", "Loop", "AndroidAPS")
- Provide general principles and strategies that can be applied with any diabetes management tools
- If the retrieved chunks don't contain relevant information, say: "No specific information found in the knowledge base for this topic."
- You may combine retrieved knowledge with the user's personal Glooko data when relevant

## CITATION FORMAT
- Do NOT use inline citations like [source: X, confidence: Y]
- At the END of your response, add a "Sources" section with this format:
  - [Source type]: [Confidence level if <0.8]
  - Example: "- Clinical guidelines (ADA 2026)" or "- Research literature (moderate confidence)"

## RESPONSE STRUCTURE FOR PATTERN + MANAGEMENT QUERIES
**MANDATORY STRUCTURE for queries about diabetes patterns (dawn phenomenon, etc.) + management:**

1. **Definition (1-2 sentences max)**: Brief explanation from educational sources
2. **Practical Management Strategies**: At least 3 concrete, numbered strategies framed as "to discuss with your healthcare team"
   - Each strategy should be general principles, not product-specific
   - Focus on: adjusting basal insulin, temporary basal adjustments, overnight glucose monitoring, target adjustments, automated insulin delivery features
   - Frame all recommendations as general approaches that work with various diabetes management systems
3. **Clinical Context (optional, 1 sentence)**: If ADA/clinical chunks exist, add "guidelines emphasize..." but don't replace practical steps

**CRITICAL RULES:**
- **NEVER definition-only**: Always include at least 3 practical strategies
- **Product-agnostic only**: Use general terms like "continuous glucose monitoring", "automated insulin delivery", "insulin pump"
- **Team consultation framing**: Every practical suggestion must be "to discuss with your healthcare team"
- **Only fall back to definition-only when NO practical chunks are retrieved**
- **General principles**: Convert specific tool recommendations to universal approaches"""
        else:
            kb_instructions = """
## Knowledge Base Status
No knowledge base results were found for this query.
- If this is an educational question about diabetes, respond: "No specific information found in the knowledge base for this topic. Please consult your healthcare provider or diabetes educator."
- DO NOT make up information or cite sources that were not retrieved"""

        glooko_instructions = ""
        if has_glooko:
            glooko_instructions = """
## Personal Data Instructions
- Use the Glooko data above when the user asks about their own readings, patterns, or trends
- You may reference this personal data without additional citations"""
        elif not has_kb_results:
            glooko_instructions = """
## Personal Data Status
No Glooko data available. If the user asks about their personal data, mention they can upload their Glooko export."""

        return f"""{context}

---

## User Question
{query}
{kb_instructions}
{glooko_instructions}

## General Guidelines
- Be conversational and helpful
- For medical decisions, remind them to consult their healthcare team
- Be concise but thorough
- NEVER invent or hallucinate references to books, papers, or external sources
- You MUST end every response with:

### Sources
- [source name]: [confidence if <0.8]"""

    def _get_disclaimer(self, answer: str, glooko_available: bool) -> str:
        """Generate appropriate disclaimer based on response content."""
        if "healthcare" in answer.lower() or "doctor" in answer.lower():
            return ""  # Already has a disclaimer

        if glooko_available:
            return "This analysis includes your personal data. Discuss any changes with your healthcare team."
        else:
            return "This is educational information. Always consult your healthcare provider."
