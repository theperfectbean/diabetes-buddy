"""
Glooko Query Agent for Diabetes Buddy

Handles natural language queries about user's personal diabetes data
from Glooko exports. Translates queries to data operations and returns
formatted answers with appropriate context and disclaimers.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .llm_provider import LLMFactory, GenerationConfig


@dataclass
class QueryIntent:
    """Parsed intent from a natural language query."""

    metric_type: str  # glucose, tir (time in range), events, trend, pattern
    aggregation: str  # average, max, min, count, percentile, distribution
    date_range: Optional[str]  # "last_week", "last_month", "jan_15_20", None (all time)
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    pattern_criteria: Optional[str] = (
        None  # "dawn_phenomenon", "post_meal", "exercise", etc.
    )
    confidence: float = 0.8


@dataclass
class QueryResult:
    """Result from a data query."""

    success: bool
    answer: str
    metric_value: Optional[Any] = None
    metric_unit: str = ""
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    data_points_used: int = 0
    warnings: List[str] = None
    context: str = ""  # Additional context about the result

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class GlookoQueryAgent:
    """
    Processes natural language queries about Glooko diabetes data.

    Workflow:
    1. Parse intent from natural language query
    2. Load latest analysis JSON file
    3. Execute query against data
    4. Format response with context and disclaimers
    """

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the Glooko Query Agent.

        Args:
            project_root: Path to project root (for finding data files)
        """
        self.llm = LLMFactory.get_provider()

        if project_root is None:
            project_root = Path(__file__).parent.parent
        else:
            project_root = Path(project_root)

        self.project_root = project_root
        self.analysis_dir = project_root / "data" / "analysis"

    def process_query(
        self,
        question: str,
        use_direct_llm: bool = True,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryResult:
        """
        Process a natural language query about user's diabetes data.

        Args:
            question: User's natural language question
            use_direct_llm: If True, use direct LLM approach (recommended).
                           If False, use legacy intent parsing approach.
            conversation_history: List of previous exchanges for context.
                Each exchange is a dict with 'query' and 'response' keys.

        Returns:
            QueryResult with answer and supporting information
        """
        if conversation_history is None:
            conversation_history = []
        # Load analysis data first (needed for both approaches)
        try:
            analysis_data = self.load_latest_analysis()
            if not analysis_data:
                return QueryResult(
                    success=False,
                    answer="No Glooko data found. Please upload your Glooko export file first to analyze your data.",
                )
        except Exception as e:
            return QueryResult(
                success=False, answer=f"Failed to load your Glooko data: {str(e)[:100]}"
            )

        # Use direct LLM approach - just give the LLM the data and question
        if use_direct_llm:
            return self._process_with_direct_llm(
                question, analysis_data, conversation_history
            )

        # Legacy approach: parse intent → route to handler
        return self._process_with_intent_parsing(question, analysis_data)

    def _process_with_direct_llm(
        self,
        question: str,
        analysis_data: dict,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryResult:
        """
        Process query by giving the LLM the data directly - no intent parsing.

        This is simpler and more flexible than the routing approach.
        The LLM sees the full data and answers naturally.

        Args:
            question: User's question
            analysis_data: Glooko analysis data
            conversation_history: List of previous exchanges for context
        """
        if conversation_history is None:
            conversation_history = []
        # Format the data as context for the LLM
        metrics = analysis_data.get("metrics", {})
        patterns = analysis_data.get("patterns", [])
        recommendations = analysis_data.get("recommendations", [])
        hourly_analysis = analysis_data.get("hourly_analysis", {})

        data_context = f"""Here is the user's diabetes data from their Glooko export:

## Metrics (Analysis Period: {metrics.get('date_range_days', 'unknown')} days)
- Total glucose readings: {metrics.get('total_glucose_readings', 0):,}
- Average glucose: {metrics.get('average_glucose', 'N/A')} {metrics.get('glucose_unit', 'mg/dL')}
- Standard deviation: {metrics.get('std_deviation', 'N/A')} {metrics.get('glucose_unit', 'mg/dL')}
- Coefficient of variation: {metrics.get('coefficient_of_variation', 'N/A')}%
- Time in range (70-180): {metrics.get('time_in_range_percent', 'N/A')}%
- Time below range (<70): {metrics.get('time_below_range_percent', 'N/A')}%
- Time above range (>180): {metrics.get('time_above_range_percent', 'N/A')}%

## Hourly Breakdown - When Highs Occur
"""
        # Add hourly high analysis if available
        highs_data = hourly_analysis.get("highs", {})
        if highs_data.get("peak_time_description"):
            data_context += (
                f"**Peak high times: {highs_data.get('peak_time_description')}**\n"
            )
            for evidence in highs_data.get("evidence", [])[:3]:
                data_context += f"- {evidence}\n"
        else:
            data_context += "- Hourly breakdown not available\n"

        data_context += "\n## Hourly Breakdown - When Lows Occur\n"
        lows_data = hourly_analysis.get("lows", {})
        if lows_data.get("peak_time_description"):
            data_context += (
                f"**Peak low times: {lows_data.get('peak_time_description')}**\n"
            )
            for evidence in lows_data.get("evidence", [])[:3]:
                data_context += f"- {evidence}\n"
        else:
            data_context += "- No significant low patterns by hour\n"

        data_context += "\n## Detected Patterns\n"
        if patterns:
            for p in patterns:
                data_context += f"- {p.get('type', 'Unknown')}: {p.get('description', '')} (confidence: {p.get('confidence', 0):.0f}%)\n"
        else:
            data_context += "- No specific patterns detected\n"

        if recommendations:
            data_context += "\n## Recommendations from Analysis\n"
            for rec in recommendations:
                data_context += f"- {rec}\n"

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
## Conversation History
(Reference previous questions if relevant, build on earlier advice, avoid repeating information already provided)
{history_section}
---END HISTORY---

"""

        prompt = f"""{data_context}
{history_prompt}
## User Question
{question}

## Instructions
Answer the user's question based on their diabetes data above. Be conversational and helpful.
- **CRITICAL: When asked about timing of highs/lows, use the HOURLY BREAKDOWN data above.**
- Give SPECIFIC times (e.g., "3PM", "2-5 PM") from the hourly breakdown - NOT vague terms like "morning" or "evening"
- If asking about lows/hypoglycemia, use the time_below_range_percent AND the hourly breakdown for lows
- If asking about highs/hyperglycemia, use the time_above_range_percent AND the hourly breakdown for highs
- If asking about patterns or timing, prioritize the hourly breakdown data over pattern names
- If the data doesn't contain what they're asking for, say so honestly
- Always end with a note that this is based on their uploaded data and to discuss with their healthcare team
- Be concise but informative"""

        try:
            answer = self.llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.7),
            )

            # Add disclaimer if not present
            if "healthcare team" not in answer.lower():
                answer += "\n\n[This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

            return QueryResult(
                success=True,
                answer=answer,
                date_range_start=analysis_data.get("analysis_date", ""),
                date_range_end=analysis_data.get("analysis_date", ""),
                data_points_used=metrics.get("total_glucose_readings", 0),
            )
        except Exception as e:
            return QueryResult(
                success=False, answer=f"Error generating response: {str(e)[:100]}"
            )

    def _process_with_intent_parsing(
        self, question: str, analysis_data: dict
    ) -> QueryResult:
        """Legacy approach: parse intent → route to specific handler."""
        # Step 1: Parse intent
        try:
            intent = self.parse_intent(question)
        except Exception as e:
            return QueryResult(
                success=False,
                answer=f"I couldn't understand your question. Please try asking about your glucose readings, time in range, averages, patterns, or trends. Error: {str(e)[:100]}",
            )

        # Step 2: Execute query
        try:
            result = self.execute_query(analysis_data, intent)
        except Exception as e:
            return QueryResult(
                success=False, answer=f"Error processing your query: {str(e)[:100]}"
            )

        # Step 3: Format response with context
        formatted = self.format_response(result, analysis_data, intent)

        return formatted

    def parse_intent(self, question: str) -> QueryIntent:
        """
        Parse the intent of a query using the configured LLM.

        Extracts:
        - What metric they're asking about (glucose, TIR, events, trend, pattern)
        - How they want it aggregated (average, max, count, etc.)
        - What time period (last week, January 15-20, etc.)

        Args:
            question: User's question

        Returns:
            QueryIntent with parsed parameters
        """
        prompt = f"""Parse this diabetes data query and extract the intent.

Query: "{question}"

Identify:
1. metric_type: What are they asking about? Choose: glucose, tir (time_in_range), events, trend, pattern
2. aggregation: How should data be aggregated? Choose: average, max, min, count, percentile, distribution
3. date_range: What time period? Choose: all_time, last_week, last_month, last_2weeks, last_3months, or specific dates (jan_15_20 for Jan 15-20)
4. pattern_criteria: If asking about patterns, what? (dawn_phenomenon, post_meal_spike, exercise_response, etc.) or null
5. confidence: How confident are you (0.0-1.0)?

Respond in JSON format:
{{
  "metric_type": "glucose|tir|events|trend|pattern",
  "aggregation": "average|max|min|count|percentile|distribution",
  "date_range": "all_time|last_week|last_month|last_2weeks|last_3months|specific_dates",
  "specific_dates": null or {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}},
  "pattern_criteria": null or "dawn_phenomenon|post_meal|exercise|stress|etc",
  "confidence": 0.8
}}

Rules:
- If they say "last week", that's 7 days from today
- If they say "this week", that's since Monday of current week
- If they mention specific dates like "Jan 15-20", parse as specific_dates
- "my glucose" or "blood sugar" = metric_type glucose
- "time in range" or "TIR" = metric_type tir
- "how many times", "how often", "how many" = aggregation count
- "when do I", "which days", "which hours" = pattern analysis
- "lows", "low blood sugar", "hypo", "hypoglycemia", "going low" = pattern_criteria "low"
- "highs", "high blood sugar", "hyper", "hyperglycemia", "spiking" = pattern_criteria "high"
- Questions about timing of lows/highs = metric_type pattern with appropriate pattern_criteria"""

        try:
            response_text = self.llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.3),
            )

            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            data = json.loads(response_text)

            intent = QueryIntent(
                metric_type=data.get("metric_type", "glucose"),
                aggregation=data.get("aggregation", "average"),
                date_range=data.get("date_range", "all_time"),
                pattern_criteria=data.get("pattern_criteria"),
                confidence=float(data.get("confidence", 0.8)),
            )

            # Keyword-based fallback: ensure common patterns aren't missed by LLM
            intent = self._apply_keyword_fallbacks(question, intent)

            # Parse specific dates if provided
            if data.get("specific_dates"):
                dates = data["specific_dates"]
                intent.date_start = datetime.fromisoformat(dates["start"])
                intent.date_end = datetime.fromisoformat(dates["end"])
            elif intent.date_range == "last_week":
                intent.date_end = datetime.now()
                intent.date_start = intent.date_end - timedelta(days=7)
            elif intent.date_range == "last_month":
                intent.date_end = datetime.now()
                intent.date_start = intent.date_end - timedelta(days=30)
            elif intent.date_range == "last_2weeks":
                intent.date_end = datetime.now()
                intent.date_start = intent.date_end - timedelta(days=14)
            elif intent.date_range == "last_3months":
                intent.date_end = datetime.now()
                intent.date_start = intent.date_end - timedelta(days=90)

            return intent

        except Exception as e:
            # Default to reasonable interpretation
            raise ValueError(f"Failed to parse query intent: {str(e)}")

    def _apply_keyword_fallbacks(
        self, question: str, intent: QueryIntent
    ) -> QueryIntent:
        """
        Apply keyword-based fallbacks to ensure common patterns aren't missed by LLM.

        This catches cases where the LLM might misinterpret queries about lows/highs
        or timing patterns.
        """
        q_lower = question.lower()

        # Detect low/hypo keywords - override pattern_criteria if found
        low_keywords = [
            "lows",
            "low blood sugar",
            "hypo",
            "hypoglycemia",
            "going low",
            "experience lows",
            "get lows",
            "having lows",
            "my lows",
        ]
        if any(kw in q_lower for kw in low_keywords):
            intent.pattern_criteria = "low"
            # If asking "when" about lows, ensure metric_type is pattern
            if any(
                timing in q_lower
                for timing in [
                    "when do",
                    "what time",
                    "which hour",
                    "which day",
                    "typically",
                ]
            ):
                intent.metric_type = "pattern"

        # Detect high/hyper keywords
        high_keywords = [
            "highs",
            "high blood sugar",
            "hyper",
            "hyperglycemia",
            "spiking",
            "spikes",
            "experience highs",
            "get highs",
            "my highs",
        ]
        if any(kw in q_lower for kw in high_keywords):
            intent.pattern_criteria = "high"
            if any(
                timing in q_lower
                for timing in [
                    "when do",
                    "what time",
                    "which hour",
                    "which day",
                    "typically",
                ]
            ):
                intent.metric_type = "pattern"

        # Detect TIR keywords
        tir_keywords = ["time in range", "tir", "in range", "time-in-range"]
        if any(kw in q_lower for kw in tir_keywords):
            intent.metric_type = "tir"

        # Detect timing/pattern questions
        timing_keywords = [
            "when do i",
            "what time do i",
            "which days",
            "which hours",
            "do i typically",
            "do i usually",
            "pattern",
        ]
        if any(kw in q_lower for kw in timing_keywords) and intent.metric_type not in [
            "pattern",
            "trend",
        ]:
            intent.metric_type = "pattern"

        # Time-of-day direction hints
        if "morning" in q_lower or "dawn" in q_lower:
            intent.metric_type = "pattern"
            intent.pattern_criteria = "high"
        if any(term in q_lower for term in ["overnight", "night", "nocturnal"]):
            intent.metric_type = "pattern"
            if intent.pattern_criteria is None or intent.pattern_criteria in [
                "overnight",
                "night",
                "nocturnal",
            ]:
                intent.pattern_criteria = "low"

        return intent

    def load_latest_analysis(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent Glooko analysis file.

        Returns:
            Parsed JSON analysis data or None if no files found
        """
        analysis_files = sorted(self.analysis_dir.glob("analysis_*.json"), reverse=True)

        if not analysis_files:
            return None

        try:
            with open(analysis_files[0], "r") as f:
                return json.load(f)
        except Exception as e:
            raise ValueError(
                f"Failed to load analysis file {analysis_files[0]}: {str(e)}"
            )

    def execute_query(
        self, analysis_data: Dict[str, Any], intent: QueryIntent
    ) -> QueryResult:
        """
        Execute a parsed query against the analysis data.

        Args:
            analysis_data: Parsed JSON analysis data
            intent: Parsed query intent

        Returns:
            QueryResult with the answer and supporting data
        """
        metrics = analysis_data.get("metrics", {})
        patterns = analysis_data.get("patterns", [])

        # Extract date range from analysis
        # The analysis file doesn't explicitly have dates, so we infer from context
        analysis_date = analysis_data.get("analysis_date", datetime.now().isoformat())
        date_range_days = metrics.get("date_range_days", 14)

        try:
            analysis_dt = datetime.fromisoformat(analysis_date.replace("Z", "+00:00"))
        except:
            analysis_dt = datetime.now()

        data_end_date = analysis_dt
        data_start_date = analysis_dt - timedelta(days=date_range_days)

        # Handle different metric types
        if intent.metric_type == "glucose":
            return self._query_glucose(metrics, intent, data_start_date, data_end_date)
        elif intent.metric_type == "tir":
            return self._query_tir(metrics, intent, data_start_date, data_end_date)
        elif intent.metric_type == "events":
            return self._query_events(
                metrics, patterns, intent, data_start_date, data_end_date
            )
        elif intent.metric_type == "pattern":
            return self._query_pattern(
                metrics, patterns, intent, data_start_date, data_end_date
            )
        elif intent.metric_type == "trend":
            return self._query_trend(
                metrics, patterns, intent, data_start_date, data_end_date
            )
        else:
            raise ValueError(f"Unknown metric type: {intent.metric_type}")

    def _query_glucose(
        self,
        metrics: Dict,
        intent: QueryIntent,
        data_start: datetime,
        data_end: datetime,
    ) -> QueryResult:
        """Query glucose average or statistics."""
        avg_glucose = metrics.get("average_glucose")
        std_dev = metrics.get("std_deviation")
        reading_count = metrics.get("total_glucose_readings", 0)
        cv = metrics.get("coefficient_of_variation")

        if avg_glucose is None:
            return QueryResult(
                success=False,
                answer="Average glucose data not available in your analysis.",
                date_range_start=data_start.strftime("%b %d, %Y"),
                date_range_end=data_end.strftime("%b %d, %Y"),
            )

        answer = f"Your average glucose was {int(avg_glucose)} mg/dL ({avg_glucose/18:.1f} mmol/L)"

        if std_dev:
            answer += f". Your readings varied by ±{std_dev:.0f} mg/dL (std dev: {std_dev:.0f})"

        if cv:
            answer += f", with {cv:.1f}% variability"

        answer += f". This is based on {reading_count} readings from {data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')}."

        answer += "\n\n[Note: This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

        # Safely format context values that may be None
        std_dev_str = f"{std_dev:.0f}" if std_dev is not None else "N/A"
        cv_str = f"{cv:.1f}" if cv is not None else "N/A"

        return QueryResult(
            success=True,
            answer=answer,
            metric_value=avg_glucose,
            metric_unit="mg/dL",
            date_range_start=data_start.strftime("%b %d, %Y"),
            date_range_end=data_end.strftime("%b %d, %Y"),
            data_points_used=reading_count,
            context=f"Standard deviation: {std_dev_str}, CV: {cv_str}%",
        )

    def _query_tir(
        self,
        metrics: Dict,
        intent: QueryIntent,
        data_start: datetime,
        data_end: datetime,
    ) -> QueryResult:
        """Query time in range and related percentages."""
        tir = metrics.get("time_in_range_percent")
        tar = metrics.get("time_above_range_percent")
        tbr = metrics.get("time_below_range_percent")
        reading_count = metrics.get("total_glucose_readings", 0)

        if tir is None:
            return QueryResult(
                success=False,
                answer="Time in range data not available in your analysis.",
            )

        answer = f"Your time in range (70-180 mg/dL) was {tir:.1f}%"

        if tar is not None:
            answer += f", with {tar:.1f}% above range"
        if tbr is not None:
            answer += f" and {tbr:.1f}% below range"

        answer += f" ({reading_count:,} readings, {data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')})."

        # Add context
        if tir >= 70:
            answer += " ✓ You met the ADA target of ≥70% time in range."
        else:
            answer += f" You're {70 - tir:.1f}% points below the ADA target of 70%."

        answer += "\n\n[Note: This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

        return QueryResult(
            success=True,
            answer=answer,
            metric_value=tir,
            metric_unit="%",
            date_range_start=data_start.strftime("%b %d, %Y"),
            date_range_end=data_end.strftime("%b %d, %Y"),
            data_points_used=reading_count,
            context=f"Above range: {tar:.1f}%, Below range: {tbr:.1f}%",
        )

    def _classify_pattern_direction(self, pattern: Dict) -> str:
        """Classify pattern as low, high, or neutral based on keywords.

        Args:
            pattern: Pattern dictionary with type and description

        Returns:
            'low', 'high', or 'neutral'
        """
        ptype = pattern.get("type", "").lower()
        pdesc = pattern.get("description", "").lower()
        combined = f"{ptype} {pdesc}"

        # Variability-only patterns are neutral
        if "variability" in combined:
            return "neutral"

        # Low pattern keywords
        low_keywords = [
            "hypo",
            "nocturnal low",
            "below range",
            "hypoglycemia",
            "low blood sugar",
            "low glucose",
            "dropping",
        ]
        if any(kw in combined for kw in low_keywords):
            return "low"

        # High pattern keywords
        high_keywords = [
            "dawn",
            "postmeal",
            "post-meal",
            "post_meal",
            "spike",
            "hyperglycemia",
            "above range",
            "high blood sugar",
            "rising",
            "elevated",
        ]
        if any(kw in combined for kw in high_keywords):
            return "high"

        return "neutral"

    def _query_events(
        self,
        metrics: Dict,
        patterns: List,
        intent: QueryIntent,
        data_start: datetime,
        data_end: datetime,
    ) -> QueryResult:
        """Query event counts (hypos, hypers, etc.)."""
        # Look for specific pattern types in patterns list
        events_found = []

        for pattern in patterns:
            if (
                "event" in pattern.get("type", "").lower()
                or "hypoglycemi" in pattern.get("type", "").lower()
            ):
                events_found.append(pattern)

        if not events_found:
            # Estimate from TBR if available
            reading_count = metrics.get("total_glucose_readings", 0)
            tbr = metrics.get("time_below_range_percent", 0)
            if reading_count and tbr:
                low_readings = int(reading_count * tbr / 100)
                if tbr < 1.0:
                    answer = (
                        f"You rarely experience lows. Your time below range was only {tbr:.1f}% "
                        f"during this period, which is about {low_readings} low readings total."
                    )
                else:
                    answer = (
                        f"Based on your time below range ({tbr:.1f}%), you likely had around "
                        f"{low_readings} low readings during this period."
                    )
            else:
                answer = "Event data not available in your analysis."

            return QueryResult(
                success=True,
                answer=answer,
                date_range_start=data_start.strftime("%b %d, %Y"),
                date_range_end=data_end.strftime("%b %d, %Y"),
                data_points_used=reading_count,
            )

        answer = "Based on your analysis:\n"
        for event in events_found:
            desc = event.get("description", "Event detected")
            affected = event.get("affected_readings", 0)
            answer += f"- {desc}: {affected} readings affected\n"

        answer += f"\nDate range: {data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')}"
        answer += "\n\n[Note: This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

        return QueryResult(
            success=True,
            answer=answer,
            date_range_start=data_start.strftime("%b %d, %Y"),
            date_range_end=data_end.strftime("%b %d, %Y"),
        )

    def _query_pattern(
        self,
        metrics: Dict,
        patterns: List,
        intent: QueryIntent,
        data_start: datetime,
        data_end: datetime,
    ) -> QueryResult:
        """Query identified patterns."""
        # Classify patterns by direction (low/high/neutral)
        low_patterns = [
            p for p in patterns if self._classify_pattern_direction(p) == "low"
        ]
        high_patterns = [
            p for p in patterns if self._classify_pattern_direction(p) == "high"
        ]
        neutral_patterns = [
            p for p in patterns if self._classify_pattern_direction(p) == "neutral"
        ]

        # Handle low/hypo pattern queries specially using TBR metrics
        if intent.pattern_criteria and intent.pattern_criteria.lower() in [
            "low",
            "hypo",
            "hypoglycemia",
            "lows",
            "hypos",
        ]:
            tbr = metrics.get("time_below_range_percent", 0)
            reading_count = metrics.get("total_glucose_readings", 0)

            if tbr < 1.0:
                answer = f"Good news! Your time below range was only {tbr:.1f}% during this period ({data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')}), which means lows were rare."
                answer += f"\n\nWith {reading_count:,} readings and {tbr:.1f}% below 70 mg/dL, you had approximately {int(reading_count * tbr / 100)} low readings total."

                # ONLY mention low patterns if detected
                if low_patterns:
                    for pattern in low_patterns:
                        answer += f"\n\n⚠️ {pattern.get('description', 'Low pattern detected')}"
                else:
                    answer += "\n\n[Note: Your current data doesn't include hourly breakdown of when lows occurred. To see timing patterns, you'd need more frequent low events to establish a pattern.]"
            else:
                low_readings = int(reading_count * tbr / 100)
                answer = f"Your time below range was {tbr:.1f}% during this period ({data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')})."
                answer += f"\n\nThis represents approximately {low_readings} low readings out of {reading_count:,} total."

                # Check for LOW patterns only
                if low_patterns:
                    for pattern in low_patterns:
                        answer += f"\n\n⚠️ {pattern.get('description', 'Low pattern detected')}"
                else:
                    answer += "\n\n[Note: For detailed timing analysis, discuss reviewing your CGM data with your healthcare team.]"

            answer += "\n\n[This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

            return QueryResult(
                success=True,
                answer=answer,
                metric_value=tbr,
                metric_unit="%",
                date_range_start=data_start.strftime("%b %d, %Y"),
                date_range_end=data_end.strftime("%b %d, %Y"),
                data_points_used=reading_count,
            )

        # Handle high/hyper pattern queries using TAR metrics
        if intent.pattern_criteria and intent.pattern_criteria.lower() in [
            "high",
            "hyper",
            "hyperglycemia",
            "highs",
            "spike",
            "spikes",
            "spiking",
        ]:
            tar = metrics.get("time_above_range_percent", 0)
            reading_count = metrics.get("total_glucose_readings", 0)
            high_readings = int(reading_count * tar / 100)

            answer = f"Your time above range was {tar:.1f}% during this period ({data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')})."
            answer += f"\n\nThis represents approximately {high_readings:,} high readings out of {reading_count:,} total."

            # Check for HIGH patterns only
            if high_patterns:
                for pattern in high_patterns:
                    answer += f"\n\n📈 **{pattern.get('type', '').replace('_', ' ').title()}**: {pattern.get('description', 'Pattern detected')} ({pattern.get('confidence', 0):.0f}% confidence)"
                    if pattern.get("recommendation"):
                        answer += f"\n→ {pattern.get('recommendation')}"

            if tar > 30:
                answer += "\n\n⚠️ Time above range is elevated. Consider discussing bolus timing, carb counting, or correction strategies with your healthcare team."

            answer += "\n\n[This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

            return QueryResult(
                success=True,
                answer=answer,
                metric_value=tar,
                metric_unit="%",
                date_range_start=data_start.strftime("%b %d, %Y"),
                date_range_end=data_end.strftime("%b %d, %Y"),
                data_points_used=reading_count,
            )

        if not patterns:
            return QueryResult(
                success=False,
                answer=f"No patterns detected in your recent data ({data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')}).",
            )

        # Filter for requested pattern if specified
        matching_patterns = patterns
        if intent.pattern_criteria:
            matching_patterns = [
                p
                for p in patterns
                if intent.pattern_criteria.lower() in p.get("type", "").lower()
            ]

        if not matching_patterns:
            return QueryResult(
                success=False,
                answer=f"No {intent.pattern_criteria} pattern detected in your recent data.",
            )

        answer = f"Patterns detected in your data ({data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')}):\n\n"

        for pattern in matching_patterns:
            ptype = pattern.get("type", "Unknown").title()
            desc = pattern.get("description", "Pattern detected")
            confidence = pattern.get("confidence", 0)
            rec = pattern.get("recommendation", "Discuss with your healthcare team")

            answer += f"**{ptype}** ({confidence:.0f}% confidence): {desc}\n"
            answer += f"→ {rec}\n\n"

        answer += "[Note: This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

        return QueryResult(
            success=True,
            answer=answer,
            date_range_start=data_start.strftime("%b %d, %Y"),
            date_range_end=data_end.strftime("%b %d, %Y"),
        )

    def _query_trend(
        self,
        metrics: Dict,
        patterns: List,
        intent: QueryIntent,
        data_start: datetime,
        data_end: datetime,
    ) -> QueryResult:
        """Query trends over time."""
        # Classify patterns by direction
        low_patterns = [
            p for p in patterns if self._classify_pattern_direction(p) == "low"
        ]
        high_patterns = [
            p for p in patterns if self._classify_pattern_direction(p) == "high"
        ]
        neutral_patterns = [
            p for p in patterns if self._classify_pattern_direction(p) == "neutral"
        ]

        # Without individual data points, we can infer trends from patterns
        answer = "Your glucose trend based on recent patterns:\n\n"

        # Check for improving/declining indicators
        tir = metrics.get("time_in_range_percent", 0)
        tar = metrics.get("time_above_range_percent", 0)
        tbr = metrics.get("time_below_range_percent", 0)

        if tir >= 70:
            answer += "✓ Your time in range is good and meeting targets.\n"
        elif tir >= 50:
            answer += (
                "• Your time in range is moderate. There's room for improvement.\n"
            )
        else:
            answer += "⚠ Your time in range is below 50%. Consider reviewing your management strategies.\n"

        if tar > 30:
            answer += "• High time above range. Discuss bolus timing or carb counting with your team.\n"

        # Separate high and low patterns when presenting
        if high_patterns:
            answer += "\n**High BG Patterns:**\n"
            for pattern in high_patterns:
                answer += f"• {pattern.get('description', 'Pattern')} ({pattern.get('confidence', 0):.0f}% confidence)\n"

        if low_patterns:
            answer += "\n**Low BG Patterns:**\n"
            for pattern in low_patterns:
                answer += f"• {pattern.get('description', 'Pattern')} ({pattern.get('confidence', 0):.0f}% confidence)\n"

        if neutral_patterns:
            answer += "\n**Other Patterns:**\n"
            for pattern in neutral_patterns:
                answer += f"• {pattern.get('description', 'Pattern')} ({pattern.get('confidence', 0):.0f}% confidence)\n"

        answer += f"\nDate range analyzed: {data_start.strftime('%b %d')} to {data_end.strftime('%b %d, %Y')}"
        answer += "\n\n[Note: This analysis is based on your uploaded Glooko data. Discuss trends with your healthcare team.]"

        return QueryResult(
            success=True,
            answer=answer,
            date_range_start=data_start.strftime("%b %d, %Y"),
            date_range_end=data_end.strftime("%b %d, %Y"),
        )

    def format_response(
        self, result: QueryResult, analysis_data: Dict[str, Any], intent: QueryIntent
    ) -> QueryResult:
        """
        Format a query result with context and disclaimers.

        Args:
            result: Raw query result
            analysis_data: Full analysis data for context
            intent: Query intent that was processed

        Returns:
            Formatted QueryResult ready for user display
        """
        # Add warnings if confidence is low
        if intent.confidence < 0.7:
            result.warnings.append(
                "⚠️ I'm not completely sure I understood your question correctly. "
                "Please rephrase if you need different information."
            )

        # Add warning if data is old
        try:
            analysis_date = datetime.fromisoformat(
                analysis_data.get("analysis_date", "").replace("Z", "+00:00")
            )
            days_old = (datetime.now(analysis_date.tzinfo) - analysis_date).days
            if days_old > 7:
                result.warnings.append(
                    f"📅 Your data is {days_old} days old. Consider uploading a fresh export for current insights."
                )
        except:
            pass

        return result
