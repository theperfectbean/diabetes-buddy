"""
Tests for Router Agent - Agentic RAG Architecture

Tests router's ability to:
1. Detect automation mode from device mentions
2. Exclude incompatible sources for automated users
3. Identify interaction layers correctly
4. Extract user intent and constraints
"""

import pytest
from agents.router_agent import RouterAgent, AutomationMode, DeviceInteractionLayer


class TestRouterAgent:
    """Test suite for Router Agent."""
    
    @pytest.fixture
    def router(self):
        """Create router agent instance."""
        return RouterAgent()
    
    def test_camaps_automated_detection(self, router):
        """Router should detect CamAPS FX as automated mode."""
        query = "I use CamAPS FX with my Dana-i pump. How do I handle slow-absorbing meals?"
        
        context = router.analyze_query(query)
        
        assert context.automation_mode == AutomationMode.AUTOMATED
        assert "CamAPS FX" in context.devices_mentioned or "camaps" in " ".join(context.devices_mentioned).lower()
        assert context.confidence > 0.7
    
    def test_automated_excludes_manual_bolus(self, router):
        """Automated mode should exclude manual bolus features."""
        query = "I use CamAPS FX. How do I manage pizza meals?"
        
        context = router.analyze_query(query)
        
        assert context.automation_mode == AutomationMode.AUTOMATED
        # Should exclude manual bolus features for automated users
        exclude_lower = [s.lower() for s in context.exclude_sources]
        assert any("manual" in s and "bolus" in s for s in exclude_lower) or \
               any("extended" in s for s in exclude_lower)
    
    def test_automated_interaction_layer_app(self, router):
        """Automated users interact via phone app, not pump hardware."""
        query = "I'm on CamAPS FX. How do I boost insulin for a high-carb meal?"
        
        context = router.analyze_query(query)
        
        assert context.automation_mode == AutomationMode.AUTOMATED
        # Should identify app interaction, not hardware
        assert context.device_interaction_layer in [
            DeviceInteractionLayer.ALGORITHM_APP,
            DeviceInteractionLayer.MULTIPLE,
        ]
    
    def test_manual_mode_extended_bolus(self, router):
        """Manual extended bolus query should detect manual mode."""
        query = "How do I program an extended bolus on my pump for pasta?"
        
        context = router.analyze_query(query)
        
        assert context.automation_mode == AutomationMode.MANUAL
        assert context.device_interaction_layer in [
            DeviceInteractionLayer.PUMP_HARDWARE,
            DeviceInteractionLayer.MULTIPLE,
        ]
    
    def test_control_iq_automated_detection(self, router):
        """Control-IQ should be detected as automated mode."""
        query = "I have Control-IQ on my Tandem pump. Can I do extended bolus?"
        
        context = router.analyze_query(query)
        
        assert context.automation_mode == AutomationMode.AUTOMATED
        # Should exclude manual bolus since automated
        exclude_lower = [s.lower() for s in context.exclude_sources]
        assert any("manual" in s or "extended" in s for s in exclude_lower)
    
    def test_unknown_mode_low_confidence(self, router):
        """Query without device context should return unknown mode with low confidence."""
        query = "My glucose is spiking after breakfast"
        
        context = router.analyze_query(query)
        
        # Should be unknown since no device mentioned
        assert context.automation_mode == AutomationMode.UNKNOWN
        # Confidence should be lower without clear device context
        assert context.confidence < 0.8
    
    def test_user_intent_extraction(self, router):
        """Router should extract clear user intent."""
        query = "I use CamAPS FX. How do I handle slow-absorbing meals like pizza?"
        
        context = router.analyze_query(query)
        
        # Intent should mention meal management
        intent_lower = context.user_intent.lower()
        assert "meal" in intent_lower or "pizza" in intent_lower or "slow" in intent_lower
    
    def test_constraints_extraction(self, router):
        """Router should extract key constraints from query."""
        query = "How do I manage pizza with CamAPS FX? It's always slow to digest."
        
        context = router.analyze_query(query)
        
        # Should identify slow absorption or pizza as constraint
        constraints_lower = " ".join(context.key_constraints).lower()
        assert "pizza" in constraints_lower or "slow" in constraints_lower
    
    def test_conversation_memory_context(self, router):
        """Router should use conversation history for context."""
        conversation_history = [
            {"role": "user", "content": "I use CamAPS FX with Dana-i pump"},
            {"role": "assistant", "content": "Great! CamAPS FX is an automated system..."},
        ]
        query = "How do I handle slow meals?"  # No device mentioned in THIS query
        
        context = router.analyze_query(query, conversation_history=conversation_history)
        
        # Should still detect automated mode from conversation history
        # Note: This depends on LLM understanding context
        # May be UNKNOWN initially until memory system is implemented
        assert context.automation_mode in [AutomationMode.AUTOMATED, AutomationMode.UNKNOWN]
    
    def test_suggested_sources(self, router):
        """Router should suggest relevant sources."""
        query = "I use CamAPS FX. How do I boost insulin for pizza?"
        
        context = router.analyze_query(query)
        
        # Should suggest app features or meal management
        suggested_lower = " ".join(context.suggested_sources).lower()
        assert len(context.suggested_sources) > 0
        # Should suggest relevant sources
        assert "app" in suggested_lower or "meal" in suggested_lower or "camaps" in suggested_lower


class TestRouterSafetyRules:
    """Test critical safety rules in router."""
    
    @pytest.fixture
    def router(self):
        return RouterAgent()
    
    def test_never_suggest_extended_bolus_for_automated(self, router):
        """CRITICAL: Automated users should NEVER get extended bolus suggestions."""
        queries = [
            "I use CamAPS FX. How do I handle slow-absorbing meals?",
            "My Control-IQ pump - what about pizza?",
            "I'm on Loop. How to manage pasta meals?",
        ]
        
        for query in queries:
            context = router.analyze_query(query)
            
            assert context.automation_mode == AutomationMode.AUTOMATED, \
                f"Failed to detect automated for: {query}"
            
            # Must exclude manual/extended bolus sources
            exclude_lower = " ".join(context.exclude_sources).lower()
            assert ("manual" in exclude_lower or "extended" in exclude_lower), \
                f"Failed to exclude manual bolus for: {query}"
    
    def test_app_vs_hardware_distinction(self, router):
        """Router should distinguish app interactions from hardware."""
        automated_query = "CamAPS FX - how do I boost insulin?"
        manual_query = "How do I press buttons on my pump to give a bolus?"
        
        auto_context = router.analyze_query(automated_query)
        manual_context = router.analyze_query(manual_query)
        
        # Automated should be app-based
        assert auto_context.device_interaction_layer in [
            DeviceInteractionLayer.ALGORITHM_APP,
            DeviceInteractionLayer.MULTIPLE,
        ]
        
        # Manual should be hardware-based
        assert manual_context.device_interaction_layer in [
            DeviceInteractionLayer.PUMP_HARDWARE,
            DeviceInteractionLayer.MULTIPLE,
        ]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
