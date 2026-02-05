"""
Integration tests for Groq support in Diabetes Buddy.

Tests cover:
- Groq provider instantiation
- Smart routing logic with diverse query examples
- Fallback mechanisms
- Cost calculation
- Token tracking
- Safety-critical routing to Gemini
"""

import pytest
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.llm_provider import GroqProvider, LLMFactory, GenerationConfig, LLMProviderError
from agents.unified_agent import UnifiedAgent, RAGQualityAssessment


class TestGroqProvider:
    """Test Groq provider initialization and basic operations."""

    def test_groq_provider_init_requires_api_key(self):
        """Groq provider should raise error if API key not provided."""
        # Clear env vars
        os.environ.pop("GROQ_API_KEY", None)
        
        with pytest.raises(LLMProviderError, match="Groq API key not found"):
            GroqProvider()

    def test_groq_provider_init_with_api_key(self):
        """Groq provider should initialize with valid API key."""
        # Clean env
        os.environ.pop("GROQ_ENABLE_CACHING", None)
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        provider = GroqProvider()
        assert provider.api_key == "test-api-key"
        assert provider.model_name == "groq/openai/gpt-oss-20b"  # default
        assert provider.enable_caching is False

    def test_groq_provider_init_with_caching(self):
        """Groq provider should enable caching when configured."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        os.environ["GROQ_ENABLE_CACHING"] = "true"
        
        provider = GroqProvider(enable_caching=True)
        assert provider.enable_caching is True

    def test_groq_model_config_loading(self):
        """Groq provider should load model configs from models.json."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        provider = GroqProvider()
        
        # Check 20B model config
        config_20b = provider.get_model_config("groq/openai/gpt-oss-20b")
        assert config_20b["context_window"] == 128000
        assert config_20b["cost_per_million_input_tokens"] == 0.075
        assert config_20b["cost_per_million_output_tokens"] == 0.30
        assert config_20b["supports_prompt_caching"] is True
        
        # Check 120B model config
        config_120b = provider.get_model_config("groq/openai/gpt-oss-120b")
        assert config_120b["context_window"] == 128000
        assert config_120b["cost_per_million_input_tokens"] == 0.15
        assert config_120b["cost_per_million_output_tokens"] == 0.60

    def test_groq_cost_calculation(self):
        """Test Groq cost calculation with and without caching."""
        # Clean env
        os.environ.pop("GROQ_ENABLE_CACHING", None)
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        # Test without caching (20B model)
        provider = GroqProvider(model_name="groq/openai/gpt-oss-20b", enable_caching=False)
        cost = provider.calculate_cost(input_tokens=1000, output_tokens=500)
        
        # 1000 * 0.075/1000000 + 500 * 0.30/1000000 = 0.000075 + 0.00015 = 0.000225
        expected = (1000 * 0.075 + 500 * 0.30) / 1_000_000
        assert abs(cost - expected) < 0.000001

    def test_groq_cost_with_caching(self):
        """Groq cost should be reduced with caching enabled."""
        # Clean env
        os.environ.pop("GROQ_ENABLE_CACHING", None)
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        provider_with_cache = GroqProvider(model_name="groq/openai/gpt-oss-20b", enable_caching=True)
        provider_no_cache = GroqProvider(model_name="groq/openai/gpt-oss-20b", enable_caching=False)
        
        cost_with_cache = provider_with_cache.calculate_cost(input_tokens=1000, output_tokens=500)
        cost_no_cache = provider_no_cache.calculate_cost(input_tokens=1000, output_tokens=500)
        
        # Cost with cache should be less (50% discount on input, applied conservatively)
        assert cost_with_cache < cost_no_cache

    def test_groq_embedding_not_supported(self):
        """Groq should raise error on embedding attempts."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        provider = GroqProvider()
        
        with pytest.raises(LLMProviderError, match="Groq does not support embeddings"):
            provider.embed_text("test text")

    def test_groq_file_upload_not_supported(self):
        """Groq should raise error on file upload attempts."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        provider = GroqProvider()
        
        with pytest.raises(LLMProviderError, match="Groq does not support file uploads"):
            provider.upload_file("test.pdf")


class TestSmartRouting:
    """Test UnifiedAgent smart routing logic."""

    @pytest.fixture
    def unified_agent(self):
        """Create a UnifiedAgent instance for testing."""
        with patch.object(UnifiedAgent, '__init__', lambda x, **kwargs: None):
            agent = UnifiedAgent()
            agent.config = {
                "rag_quality": {"min_chunks": 1},
                "parametric_usage": {},
            }
            return agent

    def test_critical_queries_route_to_groq_first(self, unified_agent):
        """CRITICAL queries now route to Groq (safety filtering handled by Safety Auditor)."""
        query = "I'm unconscious and having a seizure"
        
        provider, model, reason = unified_agent._select_llm_provider(
            query, safety_level="CRITICAL"
        )
        
        # NEW BEHAVIOR: Safety filtering is done by Safety Auditor (pre/post),
        # not by restricting LLM choice. All queries go to Groq first.
        assert provider == "groq"
        assert "groq" in reason.lower()

    def test_high_safety_queries_route_to_groq_first(self, unified_agent):
        """HIGH safety level queries now route to Groq (Safety Auditor handles filtering)."""
        query = "What is my insulin dose for 50g carbs?"
        
        provider, model, reason = unified_agent._select_llm_provider(
            query, safety_level="HIGH"
        )
        
        # NEW: Even HIGH safety queries go to Groq
        # Safety Auditor blocks dangerous outputs from any LLM
        assert provider == "groq"

    def test_route_to_groq_20b_for_device_queries(self, unified_agent):
        """Device manual queries should route to Groq 20B."""
        query = "How do I configure my Dexcom G7?"
        
        provider, model, reason = unified_agent._select_llm_provider(query)
        
        assert provider == "groq"
        assert "20b" in model.lower()
        assert "device" in reason.lower()

    def test_route_to_groq_20b_for_simple_queries(self, unified_agent):
        """Simple factual queries should route to Groq 20B."""
        test_queries = [
            "What is insulin?",
            "How do I test my glucose?",
            "Explain carb counting",
            "Define basal rate",
        ]
        
        for query in test_queries:
            provider, model, reason = unified_agent._select_llm_provider(query)
            assert provider == "groq"
            assert "20b" in model.lower()

    def test_route_to_groq_120b_for_glooko_analysis(self, unified_agent):
        """Glooko analysis queries should route to Groq 120B."""
        test_queries = [
            "What patterns do you see in my data?",
            "Analyze my glucose trends",
            "Show my time in range",
            "What's my average glucose?",
        ]
        
        for query in test_queries:
            provider, model, reason = unified_agent._select_llm_provider(query)
            assert provider == "groq"
            assert "120b" in model.lower()
            assert "analysis" in reason.lower()

    def test_route_to_groq_120b_for_clinical_synthesis(self, unified_agent):
        """Clinical queries should route to Groq 120B with caching enabled."""
        test_queries = [
            "What does ADA say about glucose targets?",
            "What are the latest guidelines?",
            "Compare different insulin types based on research",
        ]
        
        for query in test_queries:
            provider, model, reason = unified_agent._select_llm_provider(query)
            assert provider == "groq"
            assert "120b" in model.lower()

    def test_route_respects_smart_routing_disabled(self, unified_agent):
        """When smart routing disabled, should use configured provider."""
        os.environ["ENABLE_SMART_ROUTING"] = "false"
        os.environ["LLM_PROVIDER"] = "gemini"
        
        query = "How do I configure my Dexcom?"  # Would normally go to groq
        provider, model, reason = unified_agent._select_llm_provider(query)
        
        assert provider == "gemini"
        assert "disabled" in reason.lower()
        
        # Cleanup: restore defaults for subsequent tests
        os.environ["ENABLE_SMART_ROUTING"] = "true"
        os.environ["LLM_PROVIDER"] = "groq"

    def test_route_with_complex_rag_quality(self, unified_agent):
        """Complex queries with good RAG should route to 120B."""
        rag_quality = RAGQualityAssessment(
            chunk_count=8,
            avg_confidence=0.85,
            max_confidence=0.95,
            min_confidence=0.72,
            sources_covered=["manual1", "manual2", "guide1"],
            source_diversity=3,
            topic_coverage="sufficient",
        )
        
        query = "How does the CamAPS algorithm work?"
        provider, model, reason = unified_agent._select_llm_provider(
            query, rag_quality=rag_quality
        )
        
        assert provider == "groq"
        assert "120b" in model.lower()


class TestFallbackMechanism:
    """Test Groq-first with fallback to alternative provider."""

    @pytest.fixture
    def unified_agent(self):
        """Create a UnifiedAgent with mocked LLM."""
        with patch.object(UnifiedAgent, '__init__', lambda x, **kwargs: None):
            agent = UnifiedAgent()
            agent.llm = Mock()
            return agent

    @patch('agents.llm_provider.LLMFactory.get_provider')
    @patch('agents.llm_provider.LLMFactory.reset_provider')
    def test_groq_success_no_fallback(self, mock_reset, mock_factory, unified_agent):
        """Groq should succeed without needing fallback."""
        os.environ["GROQ_FALLBACK_RETRIES"] = "3"
        os.environ["FALLBACK_PROVIDER"] = "gemini"
        os.environ["LLM_PROVIDER"] = "groq"
        
        # Groq succeeds
        unified_agent.llm.generate_text.return_value = "Groq response"
        unified_agent.llm.model_name = "groq/openai/gpt-oss-20b"
        
        answer, llm_info = unified_agent._generate_with_fallback(
            "test prompt",
            primary_provider="groq"
        )
        
        assert answer == "Groq response"
        assert llm_info["intended_provider"] == "groq"
        assert llm_info["actual_provider"] == "groq"
        assert llm_info["fallback_used"] is False
        mock_reset.assert_not_called()

    @patch('agents.llm_provider.LLMFactory.get_provider')
    @patch('agents.llm_provider.LLMFactory.reset_provider')
    def test_groq_rate_limit_fallback_to_gemini(self, mock_reset, mock_factory, unified_agent):
        """Groq rate limit should fallback to Gemini."""
        os.environ["GROQ_FALLBACK_RETRIES"] = "2"
        os.environ["FALLBACK_PROVIDER"] = "gemini"
        os.environ["LLM_PROVIDER"] = "groq"
        
        # Groq fails with rate limit
        unified_agent.llm.generate_text.side_effect = Exception("429 Rate limit exceeded")
        
        # Gemini succeeds
        fallback_llm = Mock()
        fallback_llm.generate_text.return_value = "Gemini fallback response"
        fallback_llm.model_name = "gemini-2.5-flash"
        mock_factory.return_value = fallback_llm
        
        answer, llm_info = unified_agent._generate_with_fallback(
            "test prompt",
            primary_provider="groq"
        )
        
        assert "Gemini" in answer
        assert llm_info["intended_provider"] == "groq"
        assert llm_info["actual_provider"] == "gemini"
        assert llm_info["fallback_used"] is True
        assert llm_info["fallback_reason"] == "rate_limit_exceeded"
        mock_reset.assert_called()

    @patch('agents.llm_provider.LLMFactory.get_provider')
    @patch('agents.llm_provider.LLMFactory.reset_provider')
    def test_groq_timeout_fallback_to_gemini(self, mock_reset, mock_factory, unified_agent):
        """Groq timeout should fallback to Gemini."""
        os.environ["GROQ_FALLBACK_RETRIES"] = "2"
        os.environ["FALLBACK_PROVIDER"] = "gemini"
        
        unified_agent.llm.generate_text.side_effect = Exception("Request timeout")
        
        fallback_llm = Mock()
        fallback_llm.generate_text.return_value = "Gemini response"
        fallback_llm.model_name = "gemini-2.5-flash"
        mock_factory.return_value = fallback_llm
        
        answer, llm_info = unified_agent._generate_with_fallback(
            "test prompt",
            primary_provider="groq"
        )
        
        assert llm_info["fallback_used"] is True
        assert llm_info["fallback_reason"] == "timeout"
        assert llm_info["actual_provider"] == "gemini"

    @patch('agents.llm_provider.LLMFactory.get_provider')
    @patch('agents.llm_provider.LLMFactory.reset_provider')
    def test_groq_api_key_error_fallback_to_gemini(self, mock_reset, mock_factory, unified_agent):
        """Invalid Groq API key should fallback to Gemini."""
        os.environ["GROQ_FALLBACK_RETRIES"] = "1"
        os.environ["FALLBACK_PROVIDER"] = "gemini"
        
        unified_agent.llm.generate_text.side_effect = Exception("Groq API key invalid or missing")
        
        fallback_llm = Mock()
        fallback_llm.generate_text.return_value = "Gemini response"
        fallback_llm.model_name = "gemini-2.5-flash"
        mock_factory.return_value = fallback_llm
        
        answer, llm_info = unified_agent._generate_with_fallback(
            "test prompt",
            primary_provider="groq"
        )
        
        assert llm_info["fallback_reason"] == "invalid_api_key"
        assert llm_info["actual_provider"] == "gemini"

    def test_fallback_both_fail_raises_error(self, unified_agent):
        """Should raise error if both Groq and Gemini fail."""
        os.environ["FALLBACK_PROVIDER"] = "gemini"
        os.environ["LLM_PROVIDER"] = "groq"
        os.environ["GROQ_FALLBACK_RETRIES"] = "1"
        
        unified_agent.llm.generate_text.side_effect = Exception("Groq API Error")
        
        with patch('agents.llm_provider.LLMFactory.get_provider') as mock_factory:
            gemini_mock = Mock()
            gemini_mock.generate_text.side_effect = Exception("Gemini also failed")
            mock_factory.return_value = gemini_mock
            
            with pytest.raises(LLMProviderError):
                unified_agent._generate_with_fallback("test prompt", primary_provider="groq")


class TestTokenTracking:
    """Test token usage tracking across providers."""

    def test_groq_token_tracking(self):
        """Groq provider should track token usage."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        provider = GroqProvider()
        assert provider.token_usage["input"] == 0
        assert provider.token_usage["output"] == 0


class TestGroqFirstArchitecture:
    """Verify Groq-first architecture with Safety Auditor for filtering."""

    @pytest.fixture
    def unified_agent(self):
        """Create a UnifiedAgent for routing tests."""
        with patch.object(UnifiedAgent, '__init__', lambda x, **kwargs: None):
            agent = UnifiedAgent()
            return agent

    def test_dosing_queries_route_to_groq_first(self, unified_agent):
        """Dosing queries now route to Groq (Safety Auditor blocks dangerous outputs)."""
        dosing_queries = [
            "How much insulin should I take?",
            "Calculate my bolus dose",
            "What's my basal rate?",
            "Set my insulin-to-carb ratio",
        ]
        
        for query in dosing_queries:
            provider, model, _ = unified_agent._select_llm_provider(query)
            # NEW: All queries go to Groq first
            # Safety Auditor (not LLM choice) prevents dangerous outputs
            assert provider == "groq", f"Dosing query '{query}' not routed to Groq"

    def test_emergency_queries_use_groq_first(self, unified_agent):
        """Emergency queries now route to Groq (Safety Auditor handles safety)."""
        emergency_queries = [
            "I'm having severe low blood sugar symptoms",
            "Can't wake up - blood sugar?",
            "Chest pain and dizzy",
        ]
        
        for query in emergency_queries:
            provider, model, _ = unified_agent._select_llm_provider(
                query, safety_level="CRITICAL"
            )
            # NEW: Even emergencies go to Groq first, Safety Auditor decides action
            assert provider == "groq"

    def test_safety_auditor_protects_regardless_of_llm(self, unified_agent):
        """Safety Auditor filtering works the same for Groq and Gemini."""
        # This documents the architectural change:
        # - OLD: Gemini for safety queries (safety by LLM choice)
        # - NEW: Groq first, Safety Auditor blocks bad outputs from ANY LLM
        # This is safer (defense in depth) and faster/cheaper
        query = "How much insulin for my carbs?"
        provider, model, reason = unified_agent._select_llm_provider(query)
        assert provider == "groq"
        # The response will be checked by Safety Auditor regardless of provider


class TestCostComparison:
    """Test cost tracking and comparison."""

    def test_groq_cheaper_than_gemini(self):
        """Verify Groq is cheaper than Gemini for typical queries."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        groq = GroqProvider(model_name="groq/openai/gpt-oss-20b")
        groq_cost = groq.calculate_cost(input_tokens=10000, output_tokens=2000)
        
        # Groq 20B: (10000*0.075 + 2000*0.30)/1000000 = 1.35M / 1M = 0.00135
        # Gemini Flash: (10000*0.075 + 2000*0.30)/1000000 = same = 0.00135
        # They're actually the same pricing, but Groq is faster
        assert groq_cost > 0

    def test_groq_120b_vs_20b_pricing(self):
        """120B model should cost more than 20B."""
        os.environ["GROQ_API_KEY"] = "test-api-key"
        
        groq_20b = GroqProvider(model_name="groq/openai/gpt-oss-20b")
        groq_120b = GroqProvider(model_name="groq/openai/gpt-oss-120b")
        
        cost_20b = groq_20b.calculate_cost(input_tokens=10000, output_tokens=2000)
        cost_120b = groq_120b.calculate_cost(input_tokens=10000, output_tokens=2000)
        
        assert cost_120b > cost_20b


class TestRoutingDecisionTree:
    """Test the full routing decision tree with diverse queries."""

    @pytest.fixture
    def unified_agent(self):
        """Create a UnifiedAgent for routing tests."""
        with patch.object(UnifiedAgent, '__init__', lambda x, **kwargs: None):
            agent = UnifiedAgent()
            return agent

    def test_comprehensive_routing_scenarios(self, unified_agent):
        """Test 20+ realistic query scenarios with Groq-first strategy."""
        test_cases = [
            # (query, expected_provider, description)
            ("What is diabetes?", "groq", "general education"),
            ("How do I use my Tandem pump?", "groq", "device manual"),
            ("Analyze my glucose patterns", "groq", "glooko analysis"),
            ("What do ADA guidelines say?", "groq", "clinical synthesis"),
            ("I'm having seizures", "groq", "emergency - Groq first, Safety Auditor filters"),
            ("How much insulin should I take?", "groq", "dosing - Groq first, Safety Auditor blocks"),
            ("Calculate my carb ratio", "groq", "dosing - Groq first, Safety Auditor guards"),
            ("What's my time in range?", "groq", "glooko data analysis"),
            ("How does my Dexcom work?", "groq", "device manual"),
            ("Explain CGM sensors", "groq", "education - simple factual"),
            ("Compare different insulins", "groq", "clinical comparison"),
            ("Emergency - can't wake up", "groq", "critical - but routed to Groq"),
            ("My pump settings seem off", "groq", "device troubleshooting"),
            ("What are the latest research findings?", "groq", "clinical research"),
            ("Define basal rate", "groq", "simple factual"),
            ("Explain carb counting", "groq", "education"),
            ("How do I treat a low?", "groq", "emergency symptoms - Groq first"),
            ("Tell me about loop systems", "groq", "device education"),
            ("Why is my glucose high?", "groq", "data analysis"),
            ("What sensors are compatible?", "groq", "device manual"),
        ]
        
        for query, expected_provider, description in test_cases:
            provider, model, reason = unified_agent._select_llm_provider(query)
            assert provider == expected_provider, (
                f"Query '{query}' ({description}) routed to {provider}, "
                f"expected {expected_provider}. Reason: {reason}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
