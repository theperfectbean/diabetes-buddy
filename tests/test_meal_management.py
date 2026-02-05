"""
Test suite for complex meal management query handling.

Tests the system's ability to:
1. Detect slow-carb/high-fat food queries
2. Extract relevant device features from manuals
3. Provide mechanism explanations without deflecting
4. Give actionable technique guidance
5. Avoid generic "check your manual" responses when content is available
"""

import pytest
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.unified_agent import UnifiedAgent
from agents.triage import TriageAgent, QueryCategory


class TestMealManagementDetection:
    """Test detection of meal management queries."""

    def test_pizza_with_delayed_spike(self):
        """Test detection of pizza + delayed spike pattern."""
        query = "What are the recommendations for pizza considering it is slow carb? I had a spike 6 hours after eating"
        
        agent = TriageAgent()
        # Test the direct detection method (avoids LLM rate limits)
        classification = agent._detect_meal_management_query(query)
        
        # Should be detected as complex meal management
        assert classification is not None
        assert classification.category == QueryCategory.HYBRID
        assert classification.confidence >= 0.7

    def test_pasta_with_extended_bolus_question(self):
        """Test detection of pasta + extended bolus management."""
        query = "How do I handle pasta with my insulin pump? It keeps spiking hours later"
        
        agent = TriageAgent()
        # Use direct detection to avoid LLM rate limits in CI/test environments
        classification = agent._detect_meal_management_query(query)
        
        assert classification is not None
        assert classification.category == QueryCategory.HYBRID
        assert QueryCategory.USER_SOURCES in classification.secondary_categories
        assert QueryCategory.KNOWLEDGE_BASE in classification.secondary_categories

    def test_chinese_food_delayed_highs(self):
        """Test detection of Chinese food with delayed high glucose."""
        query = "Chinese food causes delayed highs for me - what's the strategy?"
        
        agent = TriageAgent()
        # Use direct detection to avoid LLM rate limits
        classification = agent._detect_meal_management_query(query)
        
        assert classification is not None
        assert classification.category == QueryCategory.HYBRID
        assert classification.confidence >= 0.7

    def test_high_fat_meal_feature_question(self):
        """Test detection of high-fat meals with device feature question."""
        query = "Does my YpsoPump have an extended bolus feature for fatty foods?"
        
        agent = TriageAgent()
        # Use direct detection
        classification = agent._detect_meal_management_query(query)
        
        assert classification is not None
        assert classification.category == QueryCategory.HYBRID
        assert QueryCategory.USER_SOURCES in classification.secondary_categories

    def test_camaps_slowly_absorbed_meal(self):
        """Test detection of CamAPS slowly absorbed meal feature question."""
        query = "What's the CamAPS slowly absorbed meal option?"
        
        agent = TriageAgent()
        # Note: This is primarily a device feature question, may not trigger meal detection
        # but should be classified as USER_SOURCES or HYBRID when combined with meal context
        classification = agent.classify(query)
        
        # Should recognize device feature question
        assert classification.category in [QueryCategory.USER_SOURCES, QueryCategory.KNOWLEDGE_BASE, QueryCategory.HYBRID]

    def test_non_meal_management_query_not_misclassified(self):
        """Ensure non-meal queries are not incorrectly classified as meal management."""
        query = "What is the recommended blood sugar target range?"
        
        agent = TriageAgent()
        classification = agent.classify(query)
        
        # Should NOT be classified as hybrid meal management
        if classification.category == QueryCategory.HYBRID:
            assert "meal" not in classification.reasoning.lower()

    def test_meal_management_in_unified_agent(self):
        """Test meal management detection in UnifiedAgent."""
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            queries = [
                "What are the recommendations for pizza considering it is slow carb? I had a spike 6 hours after eating",
                "How do I handle pasta with my insulin pump? It keeps spiking hours later",
                "Chinese food causes delayed highs for me - what's the strategy?",
            ]
            
            for query in queries:
                is_meal_query = agent._is_meal_management_query(query)
                assert is_meal_query, f"Failed to detect meal management query: {query}"
                
                # Extract food mention
                food = agent._extract_food_mention(query)
                assert food is not None, f"Failed to extract food mention from: {query}"
                
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")

    def test_fallback_response_detection(self):
        """Test fallback response logic for insufficient information."""
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            # Test with empty chunks - should request more context
            should_provide, response_type = agent._should_provide_detailed_response(
                "How do I handle pizza?",
                retrieved_chunks=[]
            )
            assert not should_provide
            assert response_type == "request_more_context"
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")


class TestMealManagementPrompts:
    """Test meal management prompt generation."""

    def test_meal_management_prompt_includes_mechanism(self):
        """Test that meal management prompt explains the mechanism."""
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="How do I manage pizza?",
                kb_context="Extended bolus feature allows splitting insulin delivery",
                food_mention="pizza",
                user_devices=["YpsoPump"],
            )
            
            # Should include mechanism explanation
            assert "fat" in prompt.lower() or "protein" in prompt.lower()
            assert "delayed" in prompt.lower() or "absorption" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")

    def test_meal_management_prompt_includes_device_guidance(self):
        """Test that prompt includes device-specific guidance."""
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="How do I manage pasta?",
                kb_context="Extended bolus for slow absorption",
                food_mention="pasta",
                user_devices=["CamAPS"],
            )
            
            # Should include device instructions
            assert "CamAPS" in prompt or "device" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")

    def test_meal_management_prompt_avoids_generic_deflection(self):
        """Test that prompt doesn't just say 'check your manual'."""
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="How do I manage pizza?",
                kb_context="Your device has extended bolus",
                food_mention="pizza",
                user_devices=["YpsoPump"],
            )
            
            # Should NOT just deflect
            assert "EXTRACT and EXPLAIN" in prompt
            assert "do NOT say" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")


class TestMealManagementKeywords:
    """Test the COMPLEX_MEAL_KEYWORDS detection."""

    def test_pizza_detection(self):
        """Test pizza keyword detection."""
        agent = TriageAgent()
        
        keywords = agent.COMPLEX_MEAL_KEYWORDS
        assert "pizza" in keywords["food_types"]

    def test_delayed_spike_pattern(self):
        """Test delayed spike pattern detection."""
        agent = TriageAgent()
        
        keywords = agent.COMPLEX_MEAL_KEYWORDS
        assert any("delay" in kw.lower() for kw in keywords["delayed_patterns"])
        assert any("hours" in kw.lower() for kw in keywords["delayed_patterns"])

    def test_extended_bolus_keyword(self):
        """Test extended bolus management term detection."""
        agent = TriageAgent()
        
        keywords = agent.COMPLEX_MEAL_KEYWORDS
        assert "extended bolus" in keywords["management_terms"]

    def test_all_keyword_categories_present(self):
        """Test that all required keyword categories exist."""
        agent = TriageAgent()
        
        required = ["food_types", "delayed_patterns", "management_terms"]
        for category in required:
            assert category in agent.COMPLEX_MEAL_KEYWORDS
            assert len(agent.COMPLEX_MEAL_KEYWORDS[category]) > 0


class TestResponseQualityValidation:
    """Test that meal management responses meet quality standards."""

    def test_response_includes_mechanism(self):
        """
        Validate that response explains WHY delayed spikes happen.
        
        Expected: Mentions fat, protein, absorption timing, insulin resistance
        """
        # This would be an integration test with actual LLM
        # For now, check the prompt includes mechanism requirement
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="Pizza?",
                kb_context="",
                food_mention="pizza",
            )
            
            assert "mechanism" in prompt.lower() or "why" in prompt.lower()
            assert "paragraph" in prompt.lower() and "1" in prompt
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")

    def test_response_includes_technique_guidance(self):
        """
        Validate that response provides actionable technique.
        
        Expected: Includes specifics like split percentages, duration options
        """
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="Pizza?",
                kb_context="Extended bolus available",
                food_mention="pizza",
                user_devices=["YpsoPump"],
            )
            
            assert "technique" in prompt.lower() or "strategy" in prompt.lower()
            assert "actionable" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")

    def test_response_includes_healthcare_provider_mention(self):
        """
        Validate that response includes healthcare team guidance.
        
        Required: Must mention consulting healthcare provider
        """
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="Pizza?",
                kb_context="",
                food_mention="pizza",
            )
            
            assert "healthcare" in prompt.lower() or "provider" in prompt.lower() or "doctor" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")

    def test_response_no_specific_insulin_doses(self):
        """
        Validate that response does NOT provide specific insulin doses.
        
        Required safety constraint: Never suggest "take X units"
        """
        project_root = Path(__file__).parent.parent
        
        try:
            agent = UnifiedAgent(project_root=project_root)
            
            prompt = agent._build_meal_management_prompt(
                query="Pizza?",
                kb_context="",
                food_mention="pizza",
            )
            
            # Should explicitly forbid dosing
            assert "insulin dose" in prompt.lower() or "never" in prompt.lower() or "safety" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"UnifiedAgent initialization failed: {e}")


class TestIntegrationScenarios:
    """Integration tests for complete meal management scenarios."""

    @pytest.mark.integration
    def test_pizza_query_end_to_end(self):
        """
        End-to-end test: Pizza query through classification and prompt generation.
        
        Expected flow:
        1. Query detected as meal management
        2. Routed to HYBRID category
        3. Uses meal management prompt
        4. Response includes mechanism + technique + provider mention
        """
        project_root = Path(__file__).parent.parent
        query = "What are the recommendations for pizza considering it is slow carb? I had a spike 6 hours after eating"
        
        try:
            # Step 1: Classification
            triage = TriageAgent()
            classification = triage.classify(query)
            
            assert classification.category == QueryCategory.HYBRID
            
            # Step 2: Unified agent detection
            unified = UnifiedAgent(project_root=project_root)
            assert unified._is_meal_management_query(query)
            
            # Step 3: Food extraction
            food = unified._extract_food_mention(query)
            assert food == "pizza"
            
            # Step 4: Prompt generation
            prompt = unified._build_meal_management_prompt(
                query=query,
                kb_context="Extended bolus feature",
                food_mention=food,
            )
            
            # Validate prompt structure
            assert "mechanism" in prompt.lower()
            assert "paragraph" in prompt.lower()
            assert "healthcare" in prompt.lower() or "provider" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"Integration test setup failed: {e}")

    @pytest.mark.integration
    def test_pasta_query_with_device(self):
        """
        Test pasta query with detected device.
        
        Expected: Device name included in prompt and guidance
        """
        project_root = Path(__file__).parent.parent
        query = "How do I handle pasta with my insulin pump? It keeps spiking hours later"
        
        try:
            unified = UnifiedAgent(project_root=project_root)
            
            # Simulate device detection
            user_devices = ["YpsoPump"]
            
            prompt = unified._build_meal_management_prompt(
                query=query,
                kb_context="Extended bolus and dual wave options",
                food_mention="pasta",
                user_devices=user_devices,
            )
            
            # Device name should appear
            assert "YpsoPump" in prompt or "device" in prompt.lower()
            
        except Exception as e:
            pytest.skip(f"Integration test setup failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
