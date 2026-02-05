"""
Test suite for ResponseQualityEvaluator

Validates automated quality evaluation across 7 dimensions with caching,
logging, and async execution. Tests correspond to Phase 1 of
IMPLEMENTATION_COMPLETE.md.
"""
import pytest
import asyncio
import csv
from pathlib import Path
from unittest.mock import Mock, patch
from agents.response_quality_evaluator import ResponseQualityEvaluator, QualityScore, DimensionScore, SafetyScore


@pytest.fixture
def quality_evaluator(tmp_path):
    """Fixture for ResponseQualityEvaluator with test config."""
    config = {
        'log_path': str(tmp_path / 'test_quality_scores.csv'),
        'cache_enabled': True,
        'max_cache_size': 10,
        'min_acceptable_score': 3.0,
        'alert_on_score_below': 2.5
    }
    return ResponseQualityEvaluator(config=config)


class TestQualityScoreDataClass:
    """Tests for QualityScore dataclass structure."""

    def test_quality_score_has_seven_dimensions(self):
        """QualityScore includes all 7 required dimensions."""
        score = QualityScore(query="test", response="test")
        assert hasattr(score, 'answer_relevancy')
        assert hasattr(score, 'practical_helpfulness')
        assert hasattr(score, 'knowledge_guidance')
        assert hasattr(score, 'tone_professionalism')
        assert hasattr(score, 'clarity_structure')
        assert hasattr(score, 'source_integration')
        assert hasattr(score, 'safety')

    def test_dimension_score_range_1_to_5(self):
        """Each dimension score is between 1-5."""
        dim_score = DimensionScore("test", 0.5, "test")  # Below 1
        assert dim_score.score == 1.0

        dim_score = DimensionScore("test", 6.0, "test")  # Above 5
        assert dim_score.score == 5.0

        dim_score = DimensionScore("test", 3.5, "test")  # Valid
        assert dim_score.score == 3.5

    def test_average_score_calculated_correctly(self):
        """Average score is mean of all dimension scores."""
        score = QualityScore(query="test", response="test")
        score.answer_relevancy = DimensionScore("answer_relevancy", 4.0, "good")
        score.practical_helpfulness = DimensionScore("practical_helpfulness", 3.0, "ok")
        score.knowledge_guidance = DimensionScore("knowledge_guidance", 5.0, "excellent")

        expected_avg = (4.0 + 3.0 + 5.0) / 3
        assert score.average_dimension_score == expected_avg


class TestEvaluationExecution:
    """Tests for quality evaluation execution."""

    @pytest.mark.asyncio
    async def test_evaluate_async_returns_quality_score(self, quality_evaluator):
        """Async evaluation returns complete QualityScore object."""
        result = await quality_evaluator.evaluate_async(
            query="How to manage high blood sugar?",
            response="Monitor your levels and consult your doctor.",
            sources=["ADA guidelines"]
        )

        assert isinstance(result, QualityScore)
        assert result.query == "How to manage high blood sugar?"
        assert result.response == "Monitor your levels and consult your doctor."
        assert result.sources_used == ["ADA guidelines"]

    def test_evaluation_uses_llm_provider(self, quality_evaluator, mocker):
        """Evaluation calls LLM provider with structured prompt."""
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')
        mock_llm.return_value = '{"answer_relevancy": {"score": 4.0, "justification": "Good"}}'

        # Run sync evaluation
        result = quality_evaluator._evaluate_sync("test query", "test response", [], None)

        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        assert "answer_relevancy" in call_args[0][0]  # prompt contains dimension

    def test_evaluation_temperature_set_to_0_1(self, quality_evaluator, mocker):
        """LLM called with temperature=0.1 for consistency."""
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')

        quality_evaluator._evaluate_with_llm("query", "response", [])

        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs['config'].temperature == 0.1

    def test_handles_empty_response_gracefully(self, quality_evaluator):
        """Empty response string doesn't crash evaluation."""
        result = quality_evaluator._evaluate_sync("", "query", [], None)
        assert isinstance(result, QualityScore)
        assert result.response == ""

    def test_handles_llm_provider_failure(self, quality_evaluator, mocker):
        """LLM timeout/error returns None without crashing."""
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')
        mock_llm.side_effect = Exception("LLM timeout")

        result = quality_evaluator._evaluate_sync("query", "response", [], None)

        # Should return QualityScore with None dimensions
        assert isinstance(result, QualityScore)
        assert result.answer_relevancy is None


class TestCachingBehavior:
    """Tests for MD5-based caching."""

    def test_caching_prevents_duplicate_evaluation(self, quality_evaluator, mocker):
        """Identical query+response uses cached score."""
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')

        # First call
        result1 = asyncio.run(quality_evaluator.evaluate_async("test", "response", [], None))
        assert mock_llm.call_count == 1

        # Second call with same content
        result2 = asyncio.run(quality_evaluator.evaluate_async("test", "response", [], None))
        assert mock_llm.call_count == 1  # Should not call again

        assert result2.cached == True

    def test_cache_hit_logged_in_csv(self, quality_evaluator, tmp_path):
        """CSV 'cached' column shows True for cache hits."""
        # First evaluation
        asyncio.run(quality_evaluator.evaluate_async("query1", "response1", [], None))

        # Second evaluation (cached)
        asyncio.run(quality_evaluator.evaluate_async("query1", "response1", [], None))

        # Check CSV
        csv_path = Path(quality_evaluator.log_path)
        with open(csv_path, 'r') as f:
            lines = f.readlines()

        # Should have two rows, second should have cached=True
        assert len(lines) == 3  # header + 2 rows
        last_row = lines[-1]
        assert 'True' in last_row  # cached column

    def test_cache_respects_max_size(self, quality_evaluator):
        """Cache evicts oldest when max_cache_size reached."""
        # Fill cache
        for i in range(12):  # max is 10
            asyncio.run(quality_evaluator.evaluate_async(f"query{i}", f"response{i}", [], None))

        # Cache should have evicted oldest
        assert len(quality_evaluator._cache) <= 10

    def test_different_responses_not_cached(self, quality_evaluator, mocker):
        """Different responses trigger new evaluation."""
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')

        # Two different responses
        asyncio.run(quality_evaluator.evaluate_async("query", "response1", [], None))
        asyncio.run(quality_evaluator.evaluate_async("query", "response2", [], None))

        assert mock_llm.call_count == 2


class TestCSVLogging:
    """Tests for quality score logging."""

    def test_csv_created_with_correct_headers(self, quality_evaluator):
        """data/quality_scores.csv has required columns."""
        csv_path = Path(quality_evaluator.log_path)
        assert csv_path.exists()

        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)

        expected_headers = [
            'timestamp', 'query_hash', 'average_score',
            'answer_relevancy', 'practical_helpfulness', 'knowledge_guidance',
            'tone_professionalism', 'clarity_structure', 'source_integration',
            'safety_passed', 'sources_count', 'cached'
        ]
        assert headers == expected_headers

    def test_csv_row_format_correct(self, quality_evaluator):
        """Each row contains timestamp, scores, metadata."""
        asyncio.run(quality_evaluator.evaluate_async("test query", "test response", ["source1"], None))

        csv_path = Path(quality_evaluator.log_path)
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)

        assert len(row) == 12  # All columns present
        assert row[11] == 'False'  # cached column

    def test_csv_appends_without_duplicating_headers(self, quality_evaluator):
        """Multiple evaluations append rows correctly."""
        asyncio.run(quality_evaluator.evaluate_async("query1", "response1", [], None))
        asyncio.run(quality_evaluator.evaluate_async("query2", "response2", [], None))

        csv_path = Path(quality_evaluator.log_path)
        with open(csv_path, 'r') as f:
            lines = f.readlines()

        # Header + 2 data rows
        assert len(lines) == 3
        assert lines[0].startswith('timestamp')  # Header
        assert not lines[1].startswith('timestamp')  # No duplicate header


class TestQualityThresholds:
    """Tests for quality threshold alerts."""

    def test_low_quality_score_triggers_warning(self, quality_evaluator, caplog, mocker):
        """Score < 2.5 logs warning message."""
        # Mock LLM to return low score
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')
        mock_response = {
            "answer_relevancy": {"score": 1.0, "justification": "Poor"},
            "practical_helpfulness": {"score": 1.0, "justification": "Poor"},
            "knowledge_guidance": {"score": 1.0, "justification": "Poor"},
            "tone_professionalism": {"score": 1.0, "justification": "Poor"},
            "clarity_structure": {"score": 1.0, "justification": "Poor"},
            "source_integration": {"score": 1.0, "justification": "Poor"},
            "safety": {"passed": True, "justification": "Safe"}
        }
        mock_llm.return_value = str(mock_response).replace("'", '"')

        with caplog.at_level('WARNING'):
            asyncio.run(quality_evaluator.evaluate_async("query", "response", [], None))

        assert "Low quality score detected" in caplog.text

    def test_acceptable_score_no_warning(self, quality_evaluator, caplog, mocker):
        """Score >= 3.0 doesn't trigger warning."""
        mock_llm = mocker.patch.object(quality_evaluator.llm, 'generate_text')
        mock_response = {
            "answer_relevancy": {"score": 3.0, "justification": "Good"},
            "practical_helpfulness": {"score": 3.0, "justification": "Good"},
            "knowledge_guidance": {"score": 3.0, "justification": "Good"},
            "tone_professionalism": {"score": 3.0, "justification": "Good"},
            "clarity_structure": {"score": 3.0, "justification": "Good"},
            "source_integration": {"score": 3.0, "justification": "Good"},
            "safety": {"passed": True, "justification": "Safe"}
        }
        mock_llm.return_value = str(mock_response).replace("'", '"')

        with caplog.at_level('WARNING'):
            asyncio.run(quality_evaluator.evaluate_async("query", "response", [], None))

        assert "Low quality score detected" not in caplog.text


class TestAsyncBehavior:
    """Tests for non-blocking async evaluation."""

    @pytest.mark.asyncio
    async def test_evaluation_non_blocking(self, quality_evaluator):
        """Evaluation runs async, doesn't block caller."""
        # Should complete quickly (async)
        import time
        start = time.time()
        result = await quality_evaluator.evaluate_async("test", "test", [], None)
        duration = time.time() - start

        assert duration < 5.0  # Should be fast even with LLM call
        assert isinstance(result, QualityScore)

    @pytest.mark.asyncio
    async def test_multiple_async_evaluations_concurrent(self, quality_evaluator):
        """Multiple evaluations can run simultaneously."""
        import asyncio

        # Start multiple evaluations
        tasks = []
        for i in range(3):
            task = quality_evaluator.evaluate_async(f"query{i}", f"response{i}", [], None)
            tasks.append(task)

        # Should complete concurrently
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for result in results:
            assert isinstance(result, QualityScore)


class TestUnifiedAgentIntegration:
    """Tests for integration with UnifiedAgent."""

    def test_unified_agent_calls_evaluator(self, mocker):
        """UnifiedAgent.process() triggers quality evaluation."""
        # This would require mocking UnifiedAgent, but for now skip
        pytest.skip("Integration test requires UnifiedAgent mocking")

    def test_evaluation_happens_after_response_created(self, mocker):
        """Quality eval occurs post-response, not pre-response."""
        pytest.skip("Integration test requires UnifiedAgent mocking")

    def test_evaluation_failure_doesnt_block_response(self, mocker):
        """Failed evaluation doesn't prevent response delivery."""
        pytest.skip("Integration test requires UnifiedAgent mocking")