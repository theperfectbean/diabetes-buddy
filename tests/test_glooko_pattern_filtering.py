"""
Test suite for Glooko Query Agent pattern direction filtering.

Tests that low BG queries don't mention high BG patterns (like dawn phenomenon),
and vice versa. This addresses the response quality issue where dawn phenomenon
was being mentioned in responses about low blood sugar.
"""

import pytest
from agents.glooko_query import GlookoQueryAgent


# Mock analysis data with:
# - Low TBR (0.3%)
# - Detected dawn phenomenon pattern
# - Some TAR elevation
MOCK_ANALYSIS_DATA = {
    "analysis_date": "2026-02-02T12:00:00Z",
    "metrics": {
        "total_glucose_readings": 2016,
        "average_glucose": 145.3,
        "std_deviation": 42.1,
        "coefficient_of_variation": 29.0,
        "time_in_range_percent": 68.5,
        "time_below_range_percent": 0.3,
        "time_above_range_percent": 31.2,
        "date_range_days": 14,
        "glucose_unit": "mg/dL"
    },
    "patterns": [
        {
            "type": "dawn_phenomenon",
            "description": "Morning glucose elevation detected between 5:00 AM and 8:00 AM",
            "confidence": 85,
            "recommendation": "Consider adjusting basal insulin or using morning correction boluses"
        }
    ],
    "recommendations": [
        "Consider adjusting morning basal rates to address dawn phenomenon"
    ]
}


class TestPatternDirectionFiltering:
    """Test that pattern filtering works correctly based on query direction."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
    
    def test_classify_pattern_direction_dawn_phenomenon(self):
        """Test that dawn phenomenon is classified as 'high'."""
        pattern = {
            "type": "dawn_phenomenon",
            "description": "Morning glucose elevation detected"
        }
        assert self.agent._classify_pattern_direction(pattern) == "high"
    
    def test_classify_pattern_direction_nocturnal_low(self):
        """Test that nocturnal low is classified as 'low'."""
        pattern = {
            "type": "nocturnal_low",
            "description": "Low blood sugar overnight"
        }
        assert self.agent._classify_pattern_direction(pattern) == "low"
    
    def test_classify_pattern_direction_postmeal_spike(self):
        """Test that postmeal spike is classified as 'high'."""
        pattern = {
            "type": "postmeal_spike",
            "description": "Glucose spike after meals"
        }
        assert self.agent._classify_pattern_direction(pattern) == "high"
    
    def test_classify_pattern_direction_neutral(self):
        """Test that non-directional patterns are classified as 'neutral'."""
        pattern = {
            "type": "variability_pattern",
            "description": "High glucose variability detected"
        }
        assert self.agent._classify_pattern_direction(pattern) == "neutral"


class TestCase1LowBGQuestionsNoDawnPhenomenon:
    """Test Case 1: Low BG Questions (Should NOT Mention Dawn Phenomenon)."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        # Mock the load_latest_analysis method
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_when_do_i_experience_lows(self):
        """Test: 'When do I typically experience lows?'"""
        result = self.agent.process_query(
            "When do I typically experience lows?",
            use_direct_llm=False
        )
        assert result.success
        assert "dawn phenomenon" not in result.answer.lower()
        assert "0.3%" in result.answer or "rare" in result.answer.lower()
    
    def test_what_time_do_i_go_low(self):
        """Test: 'What time of day do I go low?'"""
        result = self.agent.process_query(
            "What time of day do I go low?",
            use_direct_llm=False
        )
        assert result.success
        assert "dawn phenomenon" not in result.answer.lower()
        assert "morning" not in result.answer.lower() or "morning high" not in result.answer.lower()
    
    def test_how_often_hypoglycemia(self):
        """Test: 'How often do I have hypoglycemia?'"""
        result = self.agent.process_query(
            "How often do I have hypoglycemia?",
            use_direct_llm=False
        )
        assert result.success
        assert "dawn phenomenon" not in result.answer.lower()
        assert "0.3%" in result.answer or "rare" in result.answer.lower()
    
    def test_nocturnal_lows(self):
        """Test: 'Do I experience nocturnal lows?'"""
        result = self.agent.process_query(
            "Do I experience nocturnal lows?",
            use_direct_llm=False
        )
        assert result.success
        assert "dawn phenomenon" not in result.answer.lower()
        # Should focus on rarity of lows, not mention dawn phenomenon


class TestCase2HighBGQuestionsShouldMentionDawnPhenomenon:
    """Test Case 2: High BG Questions (Should Mention Dawn Phenomenon)."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_when_do_i_go_high(self):
        """Test: 'When do I typically go high?'"""
        result = self.agent.process_query(
            "When do I typically go high?",
            use_direct_llm=False
        )
        assert result.success
        assert "dawn phenomenon" in result.answer.lower() or "morning" in result.answer.lower()
        assert "31.2%" in result.answer or "31" in result.answer
    
    def test_do_i_have_dawn_phenomenon(self):
        """Test: 'Do I have a dawn phenomenon pattern?'"""
        result = self.agent.process_query(
            "Do I have a dawn phenomenon pattern?",
            use_direct_llm=False
        )
        assert result.success
        assert "dawn" in result.answer.lower()
    
    def test_what_causes_morning_highs(self):
        """Test: 'What causes my morning highs?'"""
        result = self.agent.process_query(
            "What causes my morning highs?",
            use_direct_llm=False
        )
        assert result.success
        # Should mention dawn phenomenon or morning elevation
        assert "dawn" in result.answer.lower() or "morning" in result.answer.lower()
    
    def test_when_is_glucose_elevated(self):
        """Test: 'When is my blood sugar elevated?'"""
        result = self.agent.process_query(
            "When is my blood sugar elevated?",
            use_direct_llm=False
        )
        assert result.success
        # Should mention time above range and possibly dawn phenomenon
        assert "above range" in result.answer.lower() or "elevated" in result.answer.lower()


class TestCase3GeneralPatternQuestions:
    """Test Case 3: General Pattern Questions (Context-Dependent)."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_what_patterns_detected(self):
        """Test: 'What patterns were detected in my data?'"""
        result = self.agent.process_query(
            "What patterns were detected in my data?",
            use_direct_llm=False
        )
        assert result.success
        # Can mention dawn phenomenon in general pattern query
        assert "dawn" in result.answer.lower() or "pattern" in result.answer.lower()
    
    def test_tell_me_about_glucose_patterns(self):
        """Test: 'Tell me about my glucose patterns'"""
        result = self.agent.process_query(
            "Tell me about my glucose patterns",
            use_direct_llm=False
        )
        assert result.success
        # Should provide pattern information


class TestCase4TimeOfDayQuestions:
    """Test Case 4: Time-of-Day Questions (Direction-Specific)."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_what_happens_overnight(self):
        """Test: 'What happens to my glucose overnight?'"""
        result = self.agent.process_query(
            "What happens to my glucose overnight?",
            use_direct_llm=False
        )
        assert result.success
        # Overnight question - should NOT mention dawn phenomenon unless asking about morning
    
    def test_how_is_glucose_in_morning(self):
        """Test: 'How is my glucose in the morning?'"""
        result = self.agent.process_query(
            "How is my glucose in the morning?",
            use_direct_llm=False
        )
        assert result.success
        # Morning question + dawn phenomenon detected -> should cite it


class TestCase5EdgeCases:
    """Test Case 5: Edge Cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_glucose_unstable(self):
        """Test: 'Why is my glucose unstable?'"""
        result = self.agent.process_query(
            "Why is my glucose unstable?",
            use_direct_llm=False
        )
        assert result.success
        # Should mention CV, standard deviation, possibly patterns
    
    def test_good_control(self):
        """Test: 'Do I have good control?'"""
        result = self.agent.process_query(
            "Do I have good control?",
            use_direct_llm=False
        )
        assert result.success
        # Should cite TIR, TBR, TAR
    
    def test_diabetes_management(self):
        """Test: 'How's my diabetes management?'"""
        result = self.agent.process_query(
            "How's my diabetes management?",
            use_direct_llm=False
        )
        assert result.success
        # General question can mention both high and low patterns if relevant


class TestCase6ContradictoryPatternMix:
    """Test Case 6: Contradictory Pattern Mix."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_when_do_i_experience_lows_with_dawn_phenomenon(self):
        """Test: 'When do I experience lows?' with dawn phenomenon but no low patterns."""
        result = self.agent.process_query(
            "When do I experience lows?",
            use_direct_llm=False
        )
        assert result.success
        # CRITICAL: Should NOT mention dawn phenomenon
        assert "dawn phenomenon" not in result.answer.lower()
        assert "rare" in result.answer.lower() or "0.3%" in result.answer
        # Should say lows are rare, not mention high BG patterns


class TestCase7NoRelevantPatterns:
    """Test Case 7: No Relevant Patterns."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.agent = GlookoQueryAgent()
        self.agent.load_latest_analysis = lambda: MOCK_ANALYSIS_DATA
    
    def test_postmeal_spikes_when_only_dawn_detected(self):
        """Test: 'Do I have postmeal spikes?' when only dawn phenomenon detected."""
        result = self.agent.process_query(
            "Do I have postmeal spikes?",
            use_direct_llm=False
        )
        assert result.success
        # Should NOT fallback to mentioning dawn phenomenon
        # Either say no postmeal pattern detected, or focus on what IS detected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
