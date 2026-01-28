"""
Unit tests for GlookoQueryAgent

Tests query intent parsing, data loading, query execution, and response formatting.
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import GlookoQueryAgent, QueryIntent, QueryResult


class TestQueryIntentParsing:
    """Test parsing of natural language queries into structured intents."""

    @pytest.fixture
    def agent(self):
        """Create a GlookoQueryAgent for testing."""
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    def test_parse_glucose_average_query(self, agent):
        """Test parsing 'What was my average glucose last week?'"""
        with patch.object(agent.llm, 'generate_text') as mock_generate:
            mock_generate.return_value = json.dumps({
                "metric_type": "glucose",
                "aggregation": "average",
                "date_range": "last_week",
                "specific_dates": None,
                "pattern_criteria": None,
                "confidence": 0.95
            })
            
            intent = agent.parse_intent("What was my average glucose last week?")
            
            assert intent.metric_type == "glucose"
            assert intent.aggregation == "average"
            assert intent.date_range == "last_week"
            assert intent.confidence == 0.95
            assert intent.date_start is not None
            assert intent.date_end is not None

    def test_parse_tir_query(self, agent):
        """Test parsing time in range query."""
        with patch.object(agent.llm, 'generate_text') as mock_generate:
            mock_generate.return_value = json.dumps({
                "metric_type": "tir",
                "aggregation": "distribution",
                "date_range": "last_month",
                "specific_dates": None,
                "pattern_criteria": None,
                "confidence": 0.92
            })
            
            intent = agent.parse_intent("What's my time in range for the past month?")
            
            assert intent.metric_type == "tir"
            assert intent.aggregation == "distribution"
            assert intent.date_range == "last_month"

    def test_parse_pattern_query(self, agent):
        """Test parsing pattern detection query."""
        with patch.object(agent.llm, 'generate_text') as mock_generate:
            mock_generate.return_value = json.dumps({
                "metric_type": "pattern",
                "aggregation": "distribution",
                "date_range": "all_time",
                "specific_dates": None,
                "pattern_criteria": "dawn_phenomenon",
                "confidence": 0.85
            })
            
            intent = agent.parse_intent("When do I typically experience dawn phenomenon?")
            
            assert intent.metric_type == "pattern"
            assert intent.pattern_criteria == "dawn_phenomenon"

    def test_parse_specific_date_range(self, agent):
        """Test parsing specific date range query."""
        with patch.object(agent.llm, 'generate_text') as mock_generate:
            mock_generate.return_value = json.dumps({
                "metric_type": "glucose",
                "aggregation": "average",
                "date_range": "specific_dates",
                "specific_dates": {
                    "start": "2026-01-15",
                    "end": "2026-01-22"
                },
                "pattern_criteria": None,
                "confidence": 0.90
            })
            
            intent = agent.parse_intent("What was my average glucose from January 15 to 22?")
            
            assert intent.metric_type == "glucose"
            assert intent.date_start == datetime(2026, 1, 15)
            assert intent.date_end == datetime(2026, 1, 22)

    def test_parse_event_count_query(self, agent):
        """Test parsing event count query."""
        with patch.object(agent.llm, 'generate_text') as mock_generate:
            mock_generate.return_value = json.dumps({
                "metric_type": "events",
                "aggregation": "count",
                "date_range": "last_week",
                "specific_dates": None,
                "pattern_criteria": None,
                "confidence": 0.88
            })
            
            intent = agent.parse_intent("How many times did I go low last week?")
            
            assert intent.metric_type == "events"
            assert intent.aggregation == "count"

    def test_parse_fails_gracefully(self, agent):
        """Test that parsing failures raise descriptive errors."""
        with patch.object(agent.llm, 'generate_text') as mock_generate:
            mock_generate.side_effect = Exception("LLM error")
            
            with pytest.raises(ValueError, match="Failed to parse query intent"):
                agent.parse_intent("Some question")


class TestDataLoading:
    """Test loading analysis data from files."""

    @pytest.fixture
    def agent(self):
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    @pytest.fixture
    def sample_analysis(self):
        """Sample analysis JSON data."""
        return {
            "success": True,
            "analysis_date": datetime.now().isoformat(),
            "file_analyzed": "export_test.zip",
            "metrics": {
                "total_glucose_readings": 1000,
                "date_range_days": 14,
                "average_glucose": 145.0,
                "std_deviation": 35.0,
                "coefficient_of_variation": 24.1,
                "time_in_range_percent": 68.5,
                "time_below_range_percent": 0.5,
                "time_above_range_percent": 31.0,
            },
            "patterns": [
                {
                    "type": "dawn_phenomenon",
                    "description": "Pattern detected",
                    "confidence": 65.0,
                    "affected_readings": 50,
                    "recommendation": "Consider discussing with your healthcare team"
                }
            ]
        }

    def test_load_latest_analysis_found(self, agent, sample_analysis, tmp_path):
        """Test loading most recent analysis file."""
        # Create temp analysis directory
        analysis_dir = tmp_path / "data" / "analysis"
        analysis_dir.mkdir(parents=True)
        
        # Write test file
        analysis_file = analysis_dir / "analysis_20260128_120000.json"
        with open(analysis_file, 'w') as f:
            json.dump(sample_analysis, f)
        
        # Update agent path
        agent.analysis_dir = analysis_dir
        
        # Load and verify
        data = agent.load_latest_analysis()
        assert data is not None
        assert data["metrics"]["average_glucose"] == 145.0

    def test_load_latest_analysis_not_found(self, agent, tmp_path):
        """Test handling when no analysis files exist."""
        # Create empty analysis directory
        analysis_dir = tmp_path / "data" / "analysis"
        analysis_dir.mkdir(parents=True)
        
        agent.analysis_dir = analysis_dir
        
        data = agent.load_latest_analysis()
        assert data is None

    def test_load_picks_most_recent(self, agent, tmp_path):
        """Test that most recent file is selected when multiple exist."""
        analysis_dir = tmp_path / "data" / "analysis"
        analysis_dir.mkdir(parents=True)
        
        # Write multiple files
        for timestamp in ["20260120_100000", "20260125_100000", "20260128_100000"]:
            file = analysis_dir / f"analysis_{timestamp}.json"
            with open(file, 'w') as f:
                json.dump({"timestamp": timestamp}, f)
        
        agent.analysis_dir = analysis_dir
        
        data = agent.load_latest_analysis()
        assert data["timestamp"] == "20260128_100000"


class TestGlucoseQuery:
    """Test glucose average queries."""

    @pytest.fixture
    def agent(self):
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    @pytest.fixture
    def sample_metrics(self):
        return {
            "average_glucose": 145.5,
            "std_deviation": 32.0,
            "coefficient_of_variation": 22.0,
            "total_glucose_readings": 1200,
        }

    def test_glucose_query_success(self, agent, sample_metrics):
        """Test successful glucose average query."""
        intent = QueryIntent(
            metric_type="glucose",
            aggregation="average",
            date_range="last_week"
        )
        intent.date_start = datetime.now() - timedelta(days=7)
        intent.date_end = datetime.now()
        
        result = agent._query_glucose(sample_metrics, intent, intent.date_start, intent.date_end)
        
        assert result.success is True
        assert "145" in result.answer  # Value present
        assert "mg/dL" in result.answer
        assert "1200" in result.answer  # Reading count

    def test_glucose_query_missing_data(self, agent):
        """Test glucose query when data is missing."""
        metrics = {"average_glucose": None}
        intent = QueryIntent(metric_type="glucose", aggregation="average", date_range="last_week")
        
        result = agent._query_glucose(metrics, intent, datetime.now() - timedelta(days=7), datetime.now())
        
        assert result.success is False
        assert "not available" in result.answer.lower()


class TestTIRQuery:
    """Test time in range queries."""

    @pytest.fixture
    def agent(self):
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    def test_tir_above_target(self, agent):
        """Test TIR query when target is met."""
        metrics = {
            "time_in_range_percent": 72.0,
            "time_above_range_percent": 25.0,
            "time_below_range_percent": 3.0,
            "total_glucose_readings": 900,
        }
        intent = QueryIntent(metric_type="tir", aggregation="distribution", date_range="last_month")
        
        result = agent._query_tir(metrics, intent, datetime.now() - timedelta(days=30), datetime.now())
        
        assert result.success is True
        assert "72" in result.answer
        assert "✓" in result.answer  # Target met indicator

    def test_tir_below_target(self, agent):
        """Test TIR query when below target."""
        metrics = {
            "time_in_range_percent": 55.0,
            "time_above_range_percent": 40.0,
            "time_below_range_percent": 5.0,
            "total_glucose_readings": 900,
        }
        intent = QueryIntent(metric_type="tir", aggregation="distribution", date_range="last_month")
        
        result = agent._query_tir(metrics, intent, datetime.now() - timedelta(days=30), datetime.now())
        
        assert result.success is True
        assert "55" in result.answer
        assert "15" in result.answer  # Points below target


class TestPatternDetection:
    """Test pattern detection queries."""

    @pytest.fixture
    def agent(self):
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    def test_pattern_detection_found(self, agent):
        """Test pattern detection when patterns exist."""
        patterns = [
            {
                "type": "dawn_phenomenon",
                "description": "Morning glucose increases",
                "confidence": 72.0,
                "recommendation": "Discuss basal adjustments with your team"
            },
            {
                "type": "post_meal_spikes",
                "description": "Glucose spikes after meals",
                "confidence": 85.0,
                "recommendation": "Review bolus timing"
            }
        ]
        metrics = {}
        intent = QueryIntent(metric_type="pattern", aggregation="distribution", date_range="all_time")
        
        result = agent._query_pattern(metrics, patterns, intent, datetime.now() - timedelta(days=30), datetime.now())
        
        assert result.success is True
        assert "72" in result.answer  # Confidence
        assert "85" in result.answer

    def test_pattern_not_detected(self, agent):
        """Test when no patterns are detected."""
        patterns = []
        metrics = {}
        intent = QueryIntent(metric_type="pattern", aggregation="distribution", date_range="all_time")
        
        result = agent._query_pattern(metrics, patterns, intent, datetime.now() - timedelta(days=30), datetime.now())
        
        assert result.success is False
        assert "no patterns detected" in result.answer.lower()

    def test_filter_pattern_criteria(self, agent):
        """Test filtering patterns by criteria."""
        patterns = [
            {"type": "dawn_phenomenon", "description": "Morning glucose", "confidence": 70.0, "recommendation": "Discuss"},
            {"type": "post_meal_spikes", "description": "After meals", "confidence": 85.0, "recommendation": "Review"},
        ]
        metrics = {}
        intent = QueryIntent(
            metric_type="pattern",
            aggregation="distribution",
            date_range="all_time",
            pattern_criteria="dawn_phenomenon"
        )
        
        result = agent._query_pattern(metrics, patterns, intent, datetime.now() - timedelta(days=30), datetime.now())
        
        assert result.success is True
        assert "70" in result.answer
        assert "85" not in result.answer  # Other pattern excluded


class TestResponseFormatting:
    """Test response formatting and context addition."""

    @pytest.fixture
    def agent(self):
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    def test_add_disclaimer_to_response(self, agent):
        """Test that disclaimers are added to responses."""
        result = QueryResult(
            success=True,
            answer="Test answer",
            metric_value=100,
            metric_unit="mg/dL"
        )
        analysis_data = {"analysis_date": datetime.now().isoformat()}
        intent = QueryIntent(metric_type="glucose", aggregation="average", date_range="all_time", confidence=0.9)
        
        formatted = agent.format_response(result, analysis_data, intent)
        
        # Disclaimer should be present
        assert formatted.warnings is not None or "disclaimer" in formatted.answer.lower()

    def test_add_warning_for_low_confidence(self, agent):
        """Test warning added when intent confidence is low."""
        result = QueryResult(
            success=True,
            answer="Test answer",
            metric_value=100
        )
        analysis_data = {"analysis_date": datetime.now().isoformat()}
        intent = QueryIntent(metric_type="glucose", aggregation="average", date_range="all_time", confidence=0.6)
        
        formatted = agent.format_response(result, analysis_data, intent)
        
        # Should have warning about uncertain parsing
        assert len(formatted.warnings) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def agent(self):
        with patch('agents.glooko_query.LLMFactory.get_provider') as mock_llm:
            mock_llm.return_value = Mock()
            return GlookoQueryAgent(project_root=Path(__file__).parent.parent)

    def test_process_query_no_data(self, agent):
        """Test processing when no Glooko data exists."""
        with patch.object(agent, 'load_latest_analysis', return_value=None):
            with patch.object(agent, 'parse_intent', return_value=QueryIntent("glucose", "average", "all_time", confidence=0.9)):
                result = agent.process_query("What was my average glucose?")
                
                assert result.success is False
                assert "no glooko data" in result.answer.lower()

    def test_process_query_intent_parse_fails(self, agent):
        """Test graceful handling of intent parse failure."""
        with patch.object(agent, 'parse_intent', side_effect=Exception("Parse error")):
            result = agent.process_query("Some ambiguous question")
            
            assert result.success is False
            assert "couldn't understand" in result.answer.lower()

    def test_future_date_query(self, agent):
        """Test handling of future date in query."""
        # This would need to be tested as part of the parse_intent
        # Future dates should not be allowed
        metrics = {"average_glucose": 145}
        intent = QueryIntent(metric_type="glucose", aggregation="average", date_range="all_time")
        intent.date_end = datetime.now() + timedelta(days=1)  # Future date
        intent.date_start = datetime.now()
        
        # The query execution should handle this gracefully
        result = agent._query_glucose(metrics, intent, intent.date_start, intent.date_end)
        # Should either reject or limit to current date
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
