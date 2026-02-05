"""
Tests for safety fallback on dosing query failures.

When Groq LLM fails on insulin dosing questions, the system should:
1. Detect the dosing query
2. Return safe fallback message instead of generic error
3. Log the safety fallback event
4. Include emergency contact guidance
"""

import sys
import pytest
from pathlib import Path
import csv
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.unified_agent import UnifiedAgent


class TestDosingQueryDetection:
    """Test the _is_dosing_query method."""
    
    def setup_method(self):
        """Initialize agent for testing."""
        self.agent = UnifiedAgent(project_root=str(project_root))
    
    def test_detects_insulin_dosing_query(self):
        """Should detect insulin dosing with numbers."""
        query = "How much insulin for 50g carbs?"
        assert self.agent._is_dosing_query(query) is True
    
    def test_detects_blood_sugar_dosing_query(self):
        """Should detect blood sugar dosing queries."""
        query = "What insulin dose for blood sugar 300?"
        assert self.agent._is_dosing_query(query) is True
    
    def test_detects_pizza_dosing_query(self):
        """Should detect meal dosing queries with numbers."""
        # Must have dosing keyword + numbers
        query = "How much insulin for a pizza (about 50g carbs)?"
        assert self.agent._is_dosing_query(query) is True
    
    def test_detects_basal_rate_query(self):
        """Should detect basal rate adjustment queries."""
        query = "What should my basal rate be at 2AM?"
        assert self.agent._is_dosing_query(query) is True
    
    def test_detects_bolus_calculator_query(self):
        """Should detect bolus calculation queries."""
        query = "Calculate bolus for 75g of pasta"
        assert self.agent._is_dosing_query(query) is True
    
    def test_rejects_query_without_numbers(self):
        """Should reject dosing keywords without numbers."""
        query = "Tell me about insulin"
        assert self.agent._is_dosing_query(query) is False
    
    def test_rejects_numbers_without_dosing_keywords(self):
        """Should reject numbers without dosing keywords."""
        query = "What was my average glucose on day 300?"
        # This contains "300" but no dosing keywords
        assert self.agent._is_dosing_query(query) is False
    
    def test_rejects_generic_question(self):
        """Should reject non-dosing queries."""
        query = "What is the best pump for my needs?"
        assert self.agent._is_dosing_query(query) is False


class TestDosingFallbackMessage:
    """Test the fallback message generation."""
    
    def setup_method(self):
        """Initialize agent for testing."""
        self.agent = UnifiedAgent(project_root=str(project_root))
    
    def test_fallback_message_exists(self):
        """Should generate a non-empty fallback message."""
        msg = self.agent._get_dosing_fallback_message()
        assert len(msg) > 0
    
    def test_fallback_includes_emergency_guidance(self):
        """Should include emergency contact guidance."""
        msg = self.agent._get_dosing_fallback_message()
        assert "emergency" in msg.lower()
        assert "911" in msg or "healthcare provider" in msg
    
    def test_fallback_includes_pump_guidance(self):
        """Should guide user to pump features."""
        msg = self.agent._get_dosing_fallback_message()
        assert "pump" in msg.lower() or "calculator" in msg.lower()
    
    def test_fallback_includes_care_team_guidance(self):
        """Should recommend contacting care team."""
        msg = self.agent._get_dosing_fallback_message()
        assert "diabetes" in msg.lower() or "care team" in msg.lower()
    
    def test_fallback_emphasizes_safety(self):
        """Should emphasize safety and avoid guessing."""
        msg = self.agent._get_dosing_fallback_message()
        assert "safety" in msg.lower() or "never guess" in msg.lower()


class TestSafetyFallbackLogging:
    """Test the safety fallback logging."""
    
    def setup_method(self):
        """Initialize agent and clean up log file."""
        self.agent = UnifiedAgent(project_root=str(project_root))
        self.log_file = self.agent.analysis_dir / "safety_fallback_log.csv"
        # Remove log file if it exists to start fresh
        if self.log_file.exists():
            self.log_file.unlink()
    
    def teardown_method(self):
        """Clean up after test."""
        # Keep log file for manual inspection
        pass
    
    def test_logging_creates_csv_file(self):
        """Should create CSV file if it doesn't exist."""
        assert not self.log_file.exists(), "Log file should not exist yet"
        
        self.agent._log_safety_fallback(
            query="How much insulin for 50g carbs?",
            error_type="test_error"
        )
        
        assert self.log_file.exists(), "Log file should be created"
    
    def test_logging_includes_headers(self):
        """Should include proper headers in CSV."""
        self.agent._log_safety_fallback(
            query="Test query",
            error_type="test_error"
        )
        
        with open(self.log_file, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
            
        expected_headers = [
            "timestamp", "query", "error_type", "fallback_triggered"
        ]
        assert headers == expected_headers, f"Expected headers {expected_headers}, got {headers}"
    
    def test_logging_records_query(self):
        """Should record the actual query."""
        test_query = "How much insulin for 50g carbs?"
        self.agent._log_safety_fallback(
            query=test_query,
            error_type="groq_error"
        )
        
        with open(self.log_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip headers
            row = next(reader)
        
        assert test_query in row, "Query should be in log"
    
    def test_logging_records_multiple_events(self):
        """Should record multiple fallback events."""
        queries = [
            "How much insulin for 50g carbs?",
            "What dose for blood sugar 300?",
            "Pizza bolus calculation?"
        ]
        
        for query in queries:
            self.agent._log_safety_fallback(
                query=query,
                error_type="groq_error"
            )
        
        with open(self.log_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip headers
            rows = list(reader)
        
        assert len(rows) == 3, f"Should have 3 log entries, got {len(rows)}"


class TestSafetyFallbackIntegration:
    """Integration tests for safety fallback in process method."""
    
    def setup_method(self):
        """Initialize agent and clean up logs."""
        self.agent = UnifiedAgent(project_root=str(project_root))
        self.log_file = self.agent.analysis_dir / "safety_fallback_log.csv"
        if self.log_file.exists():
            self.log_file.unlink()
    
    def test_fallback_message_includes_required_elements(self):
        """Verify fallback message has all required safety elements."""
        msg = self.agent._get_dosing_fallback_message()
        
        # Check for required elements
        assert "bolus" in msg.lower() or "calculator" in msg.lower()
        assert "diabetes care team" in msg.lower() or "care team" in msg.lower()
        assert "emergency" in msg.lower()
        assert "911" in msg or "healthcare provider" in msg
        assert "never guess" in msg.lower() or "don't guess" in msg.lower()
    
    def test_fallback_message_is_readable(self):
        """Verify fallback message is clear and actionable."""
        msg = self.agent._get_dosing_fallback_message()
        
        # Check readability
        assert len(msg) > 100, "Message should be substantial"
        assert len(msg) < 1000, "Message should be concise"
        assert msg.count("\n") >= 2, "Message should have line breaks for readability"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
