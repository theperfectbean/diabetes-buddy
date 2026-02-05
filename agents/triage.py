"""
Triage Agent for Diabetes Buddy

Routes user queries to appropriate knowledge sources based on classification.
Uses the configured LLM for lightweight query analysis.
"""

# Force IPv4 before any Google API imports
from . import network  # noqa: F401

import os
import json
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

from .llm_provider import LLMFactory, GenerationConfig

# Try ChromaDB backend first, fallback to legacy File API
try:
    from .researcher_chromadb import ResearcherAgent, SearchResult

    CHROMADB_AVAILABLE = True
except ImportError:
    from .researcher import ResearcherAgent, SearchResult

    CHROMADB_AVAILABLE = False
    import sys

    print(
        "⚠️  ChromaDB not installed. Using legacy File API (slower).", file=sys.stderr
    )
    print("   Install with: pip install chromadb", file=sys.stderr)


class QueryCategory(Enum):
    """Categories for routing queries to knowledge sources."""

    GLOOKO_DATA = "glooko_data"  # Personal Glooko diabetes data queries
    CLINICAL_GUIDELINES = (
        "clinical_guidelines"  # Evidence-based clinical recommendations
    )
    USER_SOURCES = "user_sources"  # User-uploaded product manuals
    KNOWLEDGE_BASE = "knowledge_base"  # Public knowledge (OpenAPS, Loop, etc.)
    HYBRID = "hybrid"  # Spans multiple domains


@dataclass
class Classification:
    """Query classification result."""

    category: QueryCategory
    confidence: float
    reasoning: str
    secondary_categories: list[QueryCategory] = field(default_factory=list)


@dataclass
class TriageResponse:
    """Structured response from the Triage Agent."""

    query: str
    classification: Classification
    results: dict[str, list[SearchResult]]
    synthesized_answer: str


class TriageAgent:
    """
    Triage Agent that classifies queries and routes them to appropriate
    knowledge sources via the ResearcherAgent.
    """

    # Confidence threshold for routing decisions
    CONFIDENCE_THRESHOLD = 0.7

    # Keywords for complex meal management queries
    # Identifies slow-carb, high-fat meals that cause delayed glucose spikes
    COMPLEX_MEAL_KEYWORDS = {
        # Food types
        "food_types": [
            "pizza", "pasta", "chinese food", "fried", "fatty", "creamy", "cheese",
            "slow carb", "high fat", "protein", "ice cream", "chow mein", "pad thai",
            "donuts", "pastry", "baked goods", "fries", "burger", "pho", "ramen",
            "meals", "meal", "food", "eating",  # Generic meal/food references
        ],
        # Symptoms/temporal patterns indicating delayed absorption
        "delayed_patterns": [
            "delayed spike", "delayed high", "hours later", "overnight spike", "slow rise",
            "still rising", "keeps going up", "spike after", "hours after eating",
            "6 hours", "5 hours", "4 hours", "3 hours", "2 hours later",
            "blood sugar keeps rising", "won't come down", "prolonged high", "continues to rise",
            "manage", "handle", "absorb",  # Action words for meal management
            "go high", "goes high", "going high", "get high",  # User phrasing for glucose rise
            "during the night", "at night", "nighttime",  # Temporal indicators
            "deal with", "tend to", "keep", "still",  # Common user expressions
        ],
        # Management/technique terms
        "management_terms": [
            "extended bolus", "combination bolus", "split dose", "dual wave",
            "slowly absorbed meal", "fat and protein", "meal boost", "ease-off",
            "carb entry", "extended delivery", "split percentage", "gradual delivery",
            "meal feature",  # General meal feature inquiry
        ]
    }

    # Category descriptions for the classifier
    CATEGORY_DESCRIPTIONS = {
        "glooko_data": "Personal diabetes data queries about user's own glucose readings, time in range, averages, patterns, trends from uploaded Glooko export files. Keywords: my glucose, my blood sugar, my time in range, my readings, last week, how many times, average, trend, pattern, dawn phenomenon, post-meal spike, when do I, do I experience, my lows, my highs, my hypos, typically, usually. IMPORTANT: Any question using 'I' or 'my' that asks about patterns, timing, frequency, or personal glucose behavior should be classified as glooko_data.",
        "clinical_guidelines": "Evidence-based clinical recommendations and standards. Keywords: 'what does evidence say about', 'clinical recommendations for', 'what do guidelines recommend', 'is there evidence for'. Technology choice questions (pump vs MDI, CGM benefits) → Australian Guidelines Section 3. Treatment targets and goals → ADA Standards Section 6. Cardiovascular/kidney/complication management → ADA Standards Sections 10-12",
        "user_sources": "Questions about user-uploaded device manuals and product guides. Pump operation, CGM usage, device-specific features.",
        "knowledge_base": "General diabetes management questions answered from public knowledge sources (OpenAPS, Loop, AndroidAPS, Wikipedia, PubMed research)",
        "hybrid": "Questions spanning multiple domains that need information from more than one source",
        "meal_management_complex": "Queries about managing slow-carb or high-fat foods that cause delayed glucose spikes. Examples: pizza, pasta, Chinese food, fried foods. May ask about extended bolus, combination bolus, or slowly absorbed meal features.",
    }

    def __init__(self, project_root=None):
        """
        Initialize the Triage Agent.

        Args:
            project_root: Path to project root (passed to ResearcherAgent)
        """
        # Get LLM provider (configured via LLM_PROVIDER env var)
        self.llm = LLMFactory.get_provider()
        self.researcher = ResearcherAgent(project_root=project_root)

    def classify(self, query: str) -> Classification:
        """
        Classify a query into one of the knowledge categories.

        Args:
            query: The user's question

        Returns:
            Classification with category, confidence, and reasoning
        """
        # First, check for complex meal management queries
        meal_classification = self._detect_meal_management_query(query)
        if meal_classification:
            logger.info(
                f"[CLASSIFY] Query routed to {meal_classification.category.value} via meal detection | "
                f"confidence={meal_classification.confidence:.2f} | "
                f"reasoning='{meal_classification.reasoning}'"
            )
            return meal_classification

        classification_prompt = f"""You are a query classifier for a diabetes management assistant.

Classify the following query into ONE primary category:

Categories:
- glooko_data: {self.CATEGORY_DESCRIPTIONS['glooko_data']}
- clinical_guidelines: {self.CATEGORY_DESCRIPTIONS['clinical_guidelines']}
- user_sources: {self.CATEGORY_DESCRIPTIONS['user_sources']}
- knowledge_base: {self.CATEGORY_DESCRIPTIONS['knowledge_base']}
- hybrid: {self.CATEGORY_DESCRIPTIONS['hybrid']}

Query: "{query}"

Respond in JSON format:
{{
  "category": "glooko_data|clinical_guidelines|user_sources|knowledge_base|hybrid",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why this category was chosen",
  "secondary_categories": ["other", "relevant", "categories"]
}}

Rules:
- Choose "glooko_data" if the query is about the USER'S OWN data/readings/patterns. This includes:
  * Questions with "my" (my glucose, my readings, my time in range, my lows, my highs)
  * Questions with "I" asking about personal patterns (when do I, do I experience, do I typically)
  * Questions about timing of personal events (when do I get lows, what time do I spike)
  * Questions about frequency (how often do I, how many times)
- Choose "clinical_guidelines" if asking about evidence, clinical recommendations, treatment targets, or what guidelines say
- Choose "user_sources" if asking about specific device features, pump operation, or CGM usage
- Choose "knowledge_base" for general diabetes management questions
- Choose "hybrid" only if the query clearly needs information from 2+ distinct sources
- Be confident (0.8+) when keywords strongly match a category
- List secondary_categories only if they might have supplementary info"""

        try:
            response_text = self.llm.generate_text(
                prompt=classification_prompt,
                config=GenerationConfig(temperature=0.3),
            )

            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            data = json.loads(response_text)

            category = QueryCategory(data["category"])
            secondary = [QueryCategory(c) for c in data.get("secondary_categories", [])]

            classification = Classification(
                category=category,
                confidence=float(data["confidence"]),
                reasoning=data["reasoning"],
                secondary_categories=secondary,
            )

            # Apply keyword fallback to catch personal data queries the LLM might miss
            classification = self._apply_glooko_fallback(query, classification)

            logger.info(
                f"[CLASSIFY] Query classified as {classification.category.value} | "
                f"confidence={classification.confidence:.2f} | "
                f"reasoning='{classification.reasoning}' | "
                f"secondary={[c.value for c in classification.secondary_categories]}"
            )

            return classification

        except Exception as e:
            # Default to hybrid if classification fails
            return Classification(
                category=QueryCategory.HYBRID,
                confidence=0.5,
                reasoning=f"Classification failed: {e}. Defaulting to hybrid search.",
                secondary_categories=[],
            )

    def _apply_glooko_fallback(
        self, query: str, classification: Classification
    ) -> Classification:
        """
        Apply keyword-based fallback to ensure personal data queries go to Glooko.

        Catches phrases like "my data", "look at my", "analyze my", etc. that
        the LLM might miss.
        """
        q_lower = query.lower()

        # Strong indicators of personal data queries
        personal_data_phrases = [
            "my data",
            "my readings",
            "my glucose",
            "my blood sugar",
            "my numbers",
            "my levels",
            "my results",
            "my cgm",
            "my time in range",
            "my tir",
            "my lows",
            "my highs",
            "look at my",
            "analyze my",
            "check my",
            "review my",
            "based on my",
            "from my",
            "in my data",
            "my glooko",
            "my patterns",
            "my trends",
            "my average",
        ]

        # Personal timing/frequency questions
        personal_pattern_phrases = [
            "when do i",
            "what time do i",
            "do i typically",
            "do i usually",
            "how often do i",
            "how many times do i",
            "am i",
            "have i been",
            "why do i",
            "where do i",
            "do i experience",
            "do i get",
        ]

        # Action/strategy requests that imply guidance on what to do next
        action_strategy_phrases = [
            "what can i do",
            "how do i",
            "what should i",
            "how can i",
            "strategies for",
            "ways to",
            "what strategies",
            "strategies work for",
        ]

        # Expand personal data indicators to include common phrasing
        personal_data_phrases.extend(
            [
                "my spikes",
                "my post-meal spikes",
                "my dawn phenomenon",
            ]
        )

        # Check for personal data indicators
        is_personal = any(phrase in q_lower for phrase in personal_data_phrases)
        is_pattern_question = any(
            phrase in q_lower for phrase in personal_pattern_phrases
        )
        is_action_request = any(phrase in q_lower for phrase in action_strategy_phrases)

        # If it's personal data AND asks for action/strategies, treat as HYBRID
        if is_personal and is_action_request:
            return Classification(
                category=QueryCategory.HYBRID,
                confidence=0.85,
                reasoning="Query requests actionable strategies based on personal data",
                secondary_categories=[
                    QueryCategory.GLOOKO_DATA,
                    QueryCategory.KNOWLEDGE_BASE,
                ],
            )

        if is_personal or is_pattern_question:
            # Override to glooko_data if not already
            if classification.category != QueryCategory.GLOOKO_DATA:
                return Classification(
                    category=QueryCategory.GLOOKO_DATA,
                    confidence=0.9,
                    reasoning=f"Keyword fallback: detected personal data query ({classification.reasoning})",
                    secondary_categories=classification.secondary_categories,
                )

        return classification

    def _detect_meal_management_query(self, query: str) -> Optional[Classification]:
        """
        Detect if query is about complex meal management (slow-carb, high-fat foods).

        Returns:
            Classification if meal management query detected, None otherwise
        """
        q_lower = query.lower()
        
        # Check for matches across all meal keyword categories
        food_type_matches = sum(1 for kw in self.COMPLEX_MEAL_KEYWORDS["food_types"] if kw in q_lower)
        delayed_pattern_matches = sum(1 for kw in self.COMPLEX_MEAL_KEYWORDS["delayed_patterns"] if kw in q_lower)
        management_term_matches = sum(1 for kw in self.COMPLEX_MEAL_KEYWORDS["management_terms"] if kw in q_lower)
        
        total_matches = food_type_matches + delayed_pattern_matches + management_term_matches
        
        # Additional pattern checks for "high" mentions related to meals
        has_meal_high_mention = (("high" in q_lower and ("food" in q_lower or "eat" in q_lower or "meal" in q_lower)) or
                                 ("spike" in q_lower and ("after" in q_lower or "later" in q_lower or "food" in q_lower)))
        
        logger.debug(
            f"[MEAL_DETECTION] Query: '{query[:60]}...' | "
            f"food_matches={food_type_matches} delayed_matches={delayed_pattern_matches} "
            f"mgmt_matches={management_term_matches} total={total_matches} "
            f"meal_high_mention={has_meal_high_mention}"
        )
        
        # Meal management query if:
        # - Has food type + delayed pattern keywords, OR
        # - Has food type + management terms, OR
        # - Has food type + (high mention or spike mention), OR
        # - Has 3+ meal-related keywords total
        if (food_type_matches > 0 and delayed_pattern_matches > 0) or \
           (food_type_matches > 0 and management_term_matches > 0) or \
           (food_type_matches > 0 and has_meal_high_mention) or \
           total_matches >= 3:
            
            confidence = min(0.95, 0.7 + (total_matches * 0.1))
            matched_foods = [kw for kw in self.COMPLEX_MEAL_KEYWORDS["food_types"] if kw in q_lower]
            
            logger.info(
                f"[MEAL_DETECTION] ✓ DETECTED - Query classified as meal management | "
                f"confidence={confidence:.2f} | "
                f"matched_foods={matched_foods} | "
                f"routing_to=HYBRID"
            )
            
            return Classification(
                category=QueryCategory.HYBRID,  # Route as HYBRID for comprehensive search
                confidence=confidence,
                reasoning=f"Complex meal management query detected: {', '.join(matched_foods) if matched_foods else 'delayed spike'} + treatment strategy",
                secondary_categories=[
                    QueryCategory.USER_SOURCES,  # Device manuals (extended/combo bolus)
                    QueryCategory.KNOWLEDGE_BASE,  # Mechanism and guidelines
                    QueryCategory.CLINICAL_GUIDELINES,  # Evidence-based timing
                ],
            )
        
        logger.debug(f"[MEAL_DETECTION] ✗ NOT a meal management query")
        return None

    def _search_categories(
        self, query: str, categories: list[QueryCategory]
    ) -> dict[str, list[SearchResult]]:
        """
        Search specified categories for relevant information (in parallel).

        Args:
            query: The search query
            categories: List of categories to search

        Returns:
            Dictionary mapping category names to search results
        """
        # Skip searching for glooko_data - will be handled separately
        if QueryCategory.GLOOKO_DATA in categories:
            categories = [c for c in categories if c != QueryCategory.GLOOKO_DATA]
            if not categories:
                return {}

        # Build list of source keys to search
        sources_to_search = []

        # Track if we need to search the knowledge base (openaps_docs, loop_docs, etc.)
        needs_knowledge_search = False

        category_to_source = {
            QueryCategory.CLINICAL_GUIDELINES: "clinical_guidelines",
            QueryCategory.KNOWLEDGE_BASE: "knowledge_base",
            QueryCategory.USER_SOURCES: "user_sources",
        }

        for category in categories:
            if category == QueryCategory.HYBRID:
                # Search all sources for hybrid queries
                sources_to_search.append("clinical_guidelines")
                needs_knowledge_search = True
            elif category == QueryCategory.KNOWLEDGE_BASE:
                needs_knowledge_search = True
            elif category == QueryCategory.USER_SOURCES:
                sources_to_search.append("user_sources")
                logger.info("Searching user device manual collections (dynamic discovery)")
            elif category in category_to_source:
                sources_to_search.append(category_to_source[category])

        # Remove duplicates while preserving order
        sources_to_search = list(dict.fromkeys(sources_to_search))

        results = {}

        # Execute legacy source searches in parallel
        if sources_to_search:
            results = self.researcher.search_multiple(query, sources_to_search)

        # For THEORY and HYBRID queries, also search the new knowledge collections
        # (openaps_docs, loop_docs, androidaps_docs, wikipedia_education, research_papers)
        if needs_knowledge_search:
            try:
                knowledge_results = self.researcher.query_knowledge(query, top_k=5)
                if knowledge_results:
                    results["knowledge_base"] = knowledge_results
            except Exception as e:
                print(f"Warning: Knowledge base search failed: {e}")

        return results

    def _synthesize_answer(
        self,
        query: str,
        classification: Classification,
        results: dict[str, list[SearchResult]],
    ) -> str:
        """
        Synthesize a coherent answer from search results.

        Args:
            query: Original query
            classification: Query classification
            results: Search results from knowledge sources

        Returns:
            Synthesized answer string
        """
        # For glooko_data queries, return empty string (will be handled by GlookoQueryAgent)
        if classification.category == QueryCategory.GLOOKO_DATA:
            return ""

        # Collect all high-confidence results
        # Use 0.35 threshold - scores vary by collection and embedding model
        CONFIDENCE_THRESHOLD = 0.35
        all_chunks = []
        for source, source_results in results.items():
            for result in source_results:
                if result.confidence >= CONFIDENCE_THRESHOLD:
                    all_chunks.append(result)

        if not all_chunks:
            return "No relevant information found in the knowledge base for this query."

        # Use the configured LLM to synthesize from chunks
        context_parts = []
        for chunk in all_chunks:
            page_info = f", Page {chunk.page_number}" if chunk.page_number else ""
            context_parts.append(f"Source: {chunk.source}{page_info}\n{chunk.quote}\n")

        context = "\n".join(context_parts)

        prompt = f"""You are a knowledgeable diabetes educator having a conversation. Answer the user's question by synthesizing information from the provided context excerpts.

Context:
{context}

User Question: {query}

Instructions:
1. Write in natural, conversational language - like explaining to a friend
2. SYNTHESIZE information from the context into flowing prose, do NOT quote large blocks verbatim
3. Use citations VERY sparingly - only 1-2 times maximum in your entire response, at the very end or when absolutely critical. DO NOT cite after every fact or paragraph. Let the information flow naturally without constant interruptions.
4. Maintain a helpful, friendly, and supportive tone
5. Be comprehensive but readable - organize information logically with good flow
6. If the context doesn't fully answer the question, acknowledge what you can and can't say
7. Do NOT provide specific insulin doses or prescriptive medical advice
8. Use "you" naturally when appropriate, and write as if speaking directly to the person

Example style: "When changing your infusion set, make sure the site is clean and dry, and it's generally recommended to rotate sites to avoid lipohypertrophy. The key steps are disconnecting from your body first, removing the old set, cleaning the area, and then applying the new one. If you notice any redness or irritation at the site, that's a sign you should move to a different location and give that area time to heal. Most experts recommend rotating through at least 4-6 different sites to prevent tissue damage."

Your synthesized answer:"""

        try:
            return self.llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.7),
            )
        except Exception as e:
            # Fallback to formatted chunks
            return "Based on the knowledge base:\n\n" + "\n\n".join(
                [
                    f"{chunk.quote} ({chunk.source}, Page {chunk.page_number})"
                    for chunk in all_chunks
                ]
            )

    def process(
        self,
        query: str,
        verbose: bool = False,
        conversation_history: Optional[list] = None,
    ) -> TriageResponse:
        """
        Process a user query through classification, search, and synthesis.

        Args:
            query: The user's question
            verbose: Show timing information
            conversation_history: List of previous exchanges for context.
                Each exchange is a dict with 'query' and 'response' keys.

        Returns:
            TriageResponse with classification, results, and synthesized answer
        """
        if conversation_history is None:
            conversation_history = []
        start_time = time.time()

        logger.info(f"[TRIAGE] Processing query: {query[:100]}")

        # Step 1: Classify the query
        t0 = time.time()
        classification = self.classify(query)
        logger.info(f"[TRIAGE] Classification: {classification.category.value} (confidence: {classification.confidence:.2f}, reasoning: {classification.reasoning[:100]})")
        if verbose:
            print(f"[Timing] Classification: {time.time() - t0:.2f}s")

        # Step 2: Determine which categories to search
        categories_to_search = [classification.category]

        # Add secondary categories if confidence is below threshold
        if classification.confidence < self.CONFIDENCE_THRESHOLD:
            categories_to_search.extend(classification.secondary_categories)

        logger.info(f"[TRIAGE] Categories to search: {[c.value for c in categories_to_search]}")

        # Step 3: Search relevant knowledge sources
        t0 = time.time()
        results = self._search_categories(query, categories_to_search)
        total_chunks = sum(len(chunks) for chunks in results.values())
        logger.info(f"[TRIAGE] Search returned {total_chunks} chunks across {len(results)} sources")
        if verbose:
            print(f"[Timing] Search: {time.time() - t0:.2f}s")

        # Step 4: Synthesize answer from results
        t0 = time.time()
        synthesized = self._synthesize_answer(query, classification, results)
        logger.info(f"[TRIAGE] Synthesized answer length: {len(synthesized)} chars")
        if len(synthesized) < 200:
            logger.warning(f"[TRIAGE] VERY SHORT ANSWER: {synthesized}")
        if verbose:
            print(f"[Timing] Synthesis: {time.time() - t0:.2f}s")
            print(f"[Timing] Total: {time.time() - start_time:.2f}s")

        return TriageResponse(
            query=query,
            classification=classification,
            results=results,
            synthesized_answer=synthesized,
        )

    def format_response(self, response: TriageResponse) -> str:
        """Format a TriageResponse as readable text."""
        output = []

        # Header
        output.append(f"Query: {response.query}")
        output.append("=" * 60)

        # Classification
        output.append(
            f"\nClassification: {response.classification.category.value.upper()}"
        )
        output.append(f"Confidence: {response.classification.confidence:.0%}")
        output.append(f"Reasoning: {response.classification.reasoning}")

        if response.classification.secondary_categories:
            secondary = ", ".join(
                c.value for c in response.classification.secondary_categories
            )
            output.append(f"Secondary: {secondary}")

        # Search Results
        output.append("\n" + "-" * 60)
        output.append("Search Results:")

        for source, results in response.results.items():
            output.append(f"\n[{source.upper()}]")
            if results:
                for r in results[:2]:  # Show top 2 per source
                    page = f" p.{r.page_number}" if r.page_number else ""
                    output.append(f"  • ({r.confidence:.0%}{page}) {r.quote[:100]}...")
            else:
                output.append("  No relevant results")

        # Synthesized Answer
        output.append("\n" + "-" * 60)
        output.append("Answer:")
        output.append(response.synthesized_answer)

        return "\n".join(output)


if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv

    # Load environment variables
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    print("=" * 60)
    print("Diabetes Buddy - Triage Agent Test")
    print("=" * 60)

    try:
        triage = TriageAgent()

        # Test queries covering different categories
        test_queries = [
            "How do I change my pump cartridge?",
            "What is the Ease-off mode in CamAPS?",
            "How do I calculate my insulin to carb ratio?",
            "My Libre sensor says 'signal loss' - what should I do?",
            "How should I prepare for exercise with my pump and CGM?",
        ]

        for query in test_queries:
            print(f"\n{'=' * 60}")
            response = triage.process(query)
            print(triage.format_response(response))

        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)

    except ValueError as e:
        print(f"Configuration error: {e}")
    except Exception as e:
        print(f"Error: {e}")
        raise
