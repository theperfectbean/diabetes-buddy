"""
Triage Agent for Diabetes Buddy

Routes user queries to appropriate knowledge sources based on classification.
Uses Gemini for lightweight query analysis.
"""

# Force IPv4 before any Google API imports
from . import network  # noqa: F401

import os
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from .llm_provider import LLMFactory, GenerationConfig

# Try ChromaDB backend first, fallback to legacy File API
try:
    from .researcher_chromadb import ResearcherAgent, SearchResult
    CHROMADB_AVAILABLE = True
except ImportError:
    from .researcher import ResearcherAgent, SearchResult
    CHROMADB_AVAILABLE = False
    import sys
    print("⚠️  ChromaDB not installed. Using legacy File API (slower).", file=sys.stderr)
    print("   Install with: pip install chromadb", file=sys.stderr)


class QueryCategory(Enum):
    """Categories for routing queries to knowledge sources."""
    THEORY = "theory"      # Diabetes management concepts, insulin strategies
    CAMAPS = "camaps"      # CamAPS FX algorithm, Boost/Ease modes
    YPSOMED = "ypsomed"    # Pump hardware, cartridge changes
    LIBRE = "libre"        # CGM sensor, readings, alarms
    GLOOKO_DATA = "glooko_data"  # Personal Glooko diabetes data queries
    CLINICAL_GUIDELINES = "clinical_guidelines"  # Evidence-based clinical recommendations
    HYBRID = "hybrid"      # Spans multiple domains


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

    # Category descriptions for the classifier
    CATEGORY_DESCRIPTIONS = {
        "theory": "Diabetes management concepts, insulin strategies, carb counting, blood sugar patterns, basal/bolus theory, correction factors, insulin sensitivity",
        "camaps": "CamAPS FX hybrid closed-loop algorithm, Boost mode, Ease-off mode, auto-mode behavior, target glucose settings, algorithm adjustments",
        "ypsomed": "Ypsomed/mylife pump hardware, cartridge changes, infusion sets, button operations, battery, priming, physical pump troubleshooting",
        "libre": "FreeStyle Libre 3 CGM sensor, sensor application, glucose readings, alarms, scanning, sensor errors, warm-up period",
        "glooko_data": "Personal diabetes data queries about user's own glucose readings, time in range, averages, patterns, trends from uploaded Glooko export files. Keywords: my glucose, my blood sugar, my time in range, my readings, last week, how many times, average, trend, pattern, dawn phenomenon, post-meal spike",
        "clinical_guidelines": "Evidence-based clinical recommendations and standards. Keywords: 'what does evidence say about', 'clinical recommendations for', 'what do guidelines recommend', 'is there evidence for'. Technology choice questions (pump vs MDI, CGM benefits) → Australian Guidelines Section 3. Treatment targets and goals → ADA Standards Section 6. Cardiovascular/kidney/complication management → ADA Standards Sections 10-12",
        "hybrid": "Questions spanning multiple domains that need information from more than one source",
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
        classification_prompt = f"""You are a query classifier for a diabetes management assistant.

Classify the following query into ONE primary category:

Categories:
- theory: {self.CATEGORY_DESCRIPTIONS['theory']}
- camaps: {self.CATEGORY_DESCRIPTIONS['camaps']}
- ypsomed: {self.CATEGORY_DESCRIPTIONS['ypsomed']}
- libre: {self.CATEGORY_DESCRIPTIONS['libre']}
- glooko_data: {self.CATEGORY_DESCRIPTIONS['glooko_data']}
- clinical_guidelines: {self.CATEGORY_DESCRIPTIONS['clinical_guidelines']}
- hybrid: {self.CATEGORY_DESCRIPTIONS['hybrid']}

Query: "{query}"

Respond in JSON format:
{{
  "category": "theory|camaps|ypsomed|libre|glooko_data|clinical_guidelines|hybrid",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why this category was chosen",
  "secondary_categories": ["other", "relevant", "categories"]
}}

Rules:
- Choose "glooko_data" if the query is about the USER'S OWN data/readings (my glucose, my readings, last week, my time in range)
- Choose "clinical_guidelines" if asking about evidence, clinical recommendations, treatment targets, or what guidelines say
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

            return Classification(
                category=category,
                confidence=float(data["confidence"]),
                reasoning=data["reasoning"],
                secondary_categories=secondary,
            )

        except Exception as e:
            # Default to hybrid if classification fails
            return Classification(
                category=QueryCategory.HYBRID,
                confidence=0.5,
                reasoning=f"Classification failed: {e}. Defaulting to hybrid search.",
                secondary_categories=[],
            )

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

        category_to_source = {
            QueryCategory.THEORY: "theory",
            QueryCategory.CAMAPS: "camaps",
            QueryCategory.YPSOMED: "ypsomed",
            QueryCategory.LIBRE: "libre",
            QueryCategory.CLINICAL_GUIDELINES: "clinical_guidelines",
        }

        for category in categories:
            if category == QueryCategory.HYBRID:
                # Search all sources for hybrid queries
                sources_to_search.extend(["theory", "camaps", "ypsomed", "libre", "clinical_guidelines"])
            elif category in category_to_source:
                sources_to_search.append(category_to_source[category])
        
        # Remove duplicates while preserving order
        sources_to_search = list(dict.fromkeys(sources_to_search))
        
        # Execute all searches in parallel
        if sources_to_search:
            return self.researcher.search_multiple(query, sources_to_search)
        
        return {}

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
        all_chunks = []
        for source, source_results in results.items():
            for result in source_results:
                if result.confidence >= 0.7:
                    all_chunks.append(result)

        if not all_chunks:
            return "No relevant information found in the knowledge base for this query."

        # Use Gemini to synthesize from chunks
        context_parts = []
        for chunk in all_chunks:
            page_info = f", Page {chunk.page_number}" if chunk.page_number else ""
            context_parts.append(
                f"Source: {chunk.source}{page_info}\n{chunk.quote}\n"
            )
        
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
            return "Based on the knowledge base:\n\n" + "\n\n".join([
                f"{chunk.quote} ({chunk.source}, Page {chunk.page_number})"
                for chunk in all_chunks
            ])

    def process(self, query: str, verbose: bool = False) -> TriageResponse:
        """
        Process a user query through classification, search, and synthesis.

        Args:
            query: The user's question
            verbose: Show timing information

        Returns:
            TriageResponse with classification, results, and synthesized answer
        """
        start_time = time.time()
        
        # Step 1: Classify the query
        t0 = time.time()
        classification = self.classify(query)
        if verbose:
            print(f"[Timing] Classification: {time.time() - t0:.2f}s")

        # Step 2: Determine which categories to search
        categories_to_search = [classification.category]

        # Add secondary categories if confidence is below threshold
        if classification.confidence < self.CONFIDENCE_THRESHOLD:
            categories_to_search.extend(classification.secondary_categories)

        # Step 3: Search relevant knowledge sources
        t0 = time.time()
        results = self._search_categories(query, categories_to_search)
        if verbose:
            print(f"[Timing] Search: {time.time() - t0:.2f}s")

        # Step 4: Synthesize answer from results
        t0 = time.time()
        synthesized = self._synthesize_answer(query, classification, results)
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
        output.append(f"\nClassification: {response.classification.category.value.upper()}")
        output.append(f"Confidence: {response.classification.confidence:.0%}")
        output.append(f"Reasoning: {response.classification.reasoning}")

        if response.classification.secondary_categories:
            secondary = ", ".join(c.value for c in response.classification.secondary_categories)
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
