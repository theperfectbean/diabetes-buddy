"""
Triage Agent for Diabetes Buddy
Routes user queries to the appropriate specialist based on query type.
"""

from typing import Literal


SpecialistType = Literal["safety", "educator", "camaps", "ypsomed", "data"]


class TriageAgent:
    """
    Routes user queries to appropriate specialists based on content analysis.

    Priority Rules (per GEMINI.md):
    - Algorithm/logic questions -> CamAPS FX specialist
    - Hardware/mechanical issues -> Ypsomed specialist
    """

    # Keywords that indicate algorithmic/software concerns
    ALGORITHM_KEYWORDS = [
        "algorithm", "adjustment", "auto-adjust", "automatic",
        "camaps", "closed-loop", "prediction", "target",
        "ease-off", "boost", "correction", "calculation",
        "app", "software", "settings", "profile", "mode"
    ]

    # Keywords that indicate hardware/mechanical concerns
    HARDWARE_KEYWORDS = [
        "pump", "ypsomed", "cartridge", "reservoir", "tubing",
        "infusion set", "cannula", "battery", "screen",
        "button", "leak", "mechanical", "hardware", "physical",
        "connector", "device", "priming", "fill"
    ]

    # Keywords that indicate safety concerns
    SAFETY_KEYWORDS = [
        "emergency", "dka", "ketones", "unconscious", "seizure",
        "severe", "dangerous", "hospital", "911", "urgent",
        "how much", "how many units", "dosage", "dose"
    ]

    # Keywords that indicate educational questions
    EDUCATOR_KEYWORDS = [
        "what is", "why does", "how does", "explain", "understand",
        "carb", "protein", "fat", "exercise", "sick day",
        "honeymoon", "dawn phenomenon", "somogyi"
    ]

    # Keywords that indicate data analysis requests
    DATA_KEYWORDS = [
        "trend", "pattern", "analyze", "graph", "chart",
        "export", "data", "report", "statistics", "average"
    ]

    def triage(self, query: str) -> SpecialistType:
        """
        Analyze user query and route to appropriate specialist.

        Args:
            query: User's question or request

        Returns:
            Specialist type to handle the query
        """
        query_lower = query.lower()

        # Priority 1: Safety checks (override everything)
        if self._contains_keywords(query_lower, self.SAFETY_KEYWORDS):
            return "safety"

        # Priority 2: Data analysis requests
        if self._contains_keywords(query_lower, self.DATA_KEYWORDS):
            return "data"

        # Priority 3: Algorithm vs Hardware differentiation
        has_algorithm = self._contains_keywords(query_lower, self.ALGORITHM_KEYWORDS)
        has_hardware = self._contains_keywords(query_lower, self.HARDWARE_KEYWORDS)

        if has_algorithm and not has_hardware:
            return "camaps"

        if has_hardware and not has_algorithm:
            return "ypsomed"

        # If both or neither, use contextual analysis
        if has_algorithm and has_hardware:
            # Prioritize CamAPS for mixed queries (algorithm takes precedence)
            return "camaps"

        # Priority 4: Educational questions
        if self._contains_keywords(query_lower, self.EDUCATOR_KEYWORDS):
            return "educator"

        # Default: Route to educator for general diabetes questions
        return "educator"

    def _contains_keywords(self, text: str, keywords: list[str]) -> bool:
        """Check if text contains any of the keywords."""
        return any(keyword in text for keyword in keywords)

    def get_routing_explanation(self, query: str) -> str:
        """
        Provide explanation for routing decision.

        Args:
            query: User's question or request

        Returns:
            Human-readable explanation of routing decision
        """
        specialist = self.triage(query)

        explanations = {
            "safety": "This query contains safety-critical keywords. Routing to Safety Auditor.",
            "camaps": "This appears to be an algorithm/software question. Routing to CamAPS FX specialist.",
            "ypsomed": "This appears to be a hardware/mechanical question. Routing to Ypsomed specialist.",
            "data": "This is a data analysis request. Routing to Data Specialist.",
            "educator": "This is a general diabetes education question. Routing to Diabetes Educator."
        }

        return explanations[specialist]


# Example usage
if __name__ == "__main__":
    triage = TriageAgent()

    # Test cases
    test_queries = [
        "Why is my pump beeping?",
        "How does the CamAPS algorithm adjust insulin?",
        "What is the dawn phenomenon?",
        "How many units should I take?",
        "Can you analyze my CGM trends?",
        "The infusion set is leaking",
        "Why did CamAPS ease off my basal?",
    ]

    for query in test_queries:
        specialist = triage.triage(query)
        print(f"Query: {query}")
        print(f"Route to: {specialist}")
        print(f"Explanation: {triage.get_routing_explanation(query)}")
        print()
