#!/usr/bin/env python3
"""
Debug script for meal management query handling.

Tests the exact failing query through triage and unified agent.
Validates that detection, routing, and response generation work correctly.

Usage:
    python scripts/debug_meal_query.py
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test query from the issue
TEST_QUERY = "how do i deal with slow carb meals? i tend to go high during the night"


def test_triage_detection():
    """Test if triage agent correctly detects meal management query."""
    print("\n" + "="*80)
    print("STEP 1: TRIAGE AGENT DETECTION")
    print("="*80)
    
    from agents.triage import TriageAgent
    
    triage = TriageAgent(project_root=str(project_root))
    
    print(f"\nQuery: '{TEST_QUERY}'")
    print("\nDetecting meal management query...")
    
    classification = triage.classify(TEST_QUERY)
    
    print(f"\n✓ Classification Result:")
    print(f"  Category: {classification.category.value}")
    print(f"  Confidence: {classification.confidence:.2f}")
    print(f"  Reasoning: {classification.reasoning}")
    print(f"  Secondary Categories: {[c.value for c in classification.secondary_categories]}")
    
    # Validate
    is_meal_query = "meal" in classification.reasoning.lower() or classification.category.value == "hybrid"
    is_high_confidence = classification.confidence >= 0.7
    
    print(f"\n✓ Validation:")
    print(f"  ✓ Detected as meal query: {is_meal_query}")
    print(f"  ✓ High confidence (>=0.7): {is_high_confidence}")
    
    return classification


def test_unified_agent_recognition():
    """Test if unified agent recognizes query as meal-related."""
    print("\n" + "="*80)
    print("STEP 2: UNIFIED AGENT MEAL RECOGNITION")
    print("="*80)
    
    from agents.unified_agent import UnifiedAgent
    
    unified = UnifiedAgent(project_root=str(project_root))
    
    print(f"\nQuery: '{TEST_QUERY}'")
    print("\nChecking if unified agent recognizes as meal management...")
    
    is_meal = unified._is_meal_management_query(TEST_QUERY)
    food = unified._extract_food_mention(TEST_QUERY)
    
    print(f"\n✓ Meal Management Detection:")
    print(f"  Is meal management query: {is_meal}")
    print(f"  Extracted food mention: {food or '(none)'}")
    
    return is_meal, food


def test_full_response_generation():
    """Test full response generation through unified agent."""
    print("\n" + "="*80)
    print("STEP 3: FULL RESPONSE GENERATION")
    print("="*80)
    
    from agents.unified_agent import UnifiedAgent
    
    unified = UnifiedAgent(project_root=str(project_root))
    
    print(f"\nQuery: '{TEST_QUERY}'")
    print("\nGenerating response...")
    
    try:
        # Process with just the required parameters
        result = unified.process(
            query=TEST_QUERY,
            session_id="debug_session",
            conversation_history=[],
        )
        
        response = result.answer if hasattr(result, 'answer') else ""
        sources_used = result.sources_used if hasattr(result, 'sources_used') else []
        
        print(f"\n✓ Response Generated ({len(response)} chars):")
        print(f"\n{response[:500]}...\n")
        
        print(f"✓ Sources Used: {sources_used}")
        
        return response, sources_used
    except Exception as e:
        logger.error(f"Error generating response: {e}", exc_info=True)
        print(f"\n✗ Error: {e}")
        return None, {}


def validate_response_criteria(response: str) -> dict:
    """Check response against success criteria."""
    print("\n" + "="*80)
    print("STEP 4: RESPONSE VALIDATION")
    print("="*80)
    
    if not response:
        print("\n✗ No response to validate")
        return {}
    
    response_lower = response.lower()
    
    criteria = {
        "mentions_delayed_spikes": "delayed" in response_lower or "spike" in response_lower or "3-6 hours" in response_lower,
        "mentions_fat_or_absorption": "fat" in response_lower or "absorption" in response_lower or "absorb" in response_lower,
        "mentions_device_feature": any(
            term in response_lower 
            for term in ["extended bolus", "slowly absorbed meal", "combination bolus", "dual wave", "camaps"]
        ),
        "avoids_basal_rate_changes": "basal rate" not in response_lower or "profile" not in response_lower,
        "avoids_occlusion_alarms": "occlusion" not in response_lower,
        "mentions_monitoring_timing": any(
            term in response_lower 
            for term in ["1-2 hours", "4-5 hours", "check glucose", "monitor"]
        ),
    }
    
    print("\n✓ Success Criteria Check:")
    for criterion, result in criteria.items():
        status = "✓" if result else "✗"
        print(f"  {status} {criterion}: {result}")
    
    # Calculate pass rate
    pass_count = sum(1 for v in criteria.values() if v)
    total = len(criteria)
    pass_rate = (pass_count / total) * 100
    
    print(f"\n✓ Overall Pass Rate: {pass_count}/{total} ({pass_rate:.0f}%)")
    
    if pass_rate >= 80:
        print("✓ RESULT: PASS - Response meets success criteria")
    else:
        print("✗ RESULT: FAIL - Response needs improvement")
    
    return criteria


def search_knowledge_base():
    """Search knowledge base for meal-related features."""
    print("\n" + "="*80)
    print("STEP 5: KNOWLEDGE BASE VERIFICATION")
    print("="*80)
    
    try:
        from agents.researcher_chromadb import ResearcherAgent
        
        researcher = ResearcherAgent(project_root=str(project_root))
        
        # Search for slowly absorbed meal - using the main search method
        print("\nSearching for 'slowly absorbed meal CamAPS FX'...")
        results = researcher.search_all_collections(
            query="slowly absorbed meal CamAPS FX",
            top_k=3,
        )
        
        print(f"✓ Found {len(results)} chunks:")
        for i, result in enumerate(results, 1):
            print(f"\n  Chunk {i}:")
            print(f"    Source: {result.source}")
            print(f"    Confidence: {result.confidence:.2f}")
            print(f"    Quote: {result.quote[:100]}...")
        
        # Search for extended bolus
        print("\n\nSearching for 'extended bolus'...")
        results2 = researcher.search_all_collections(
            query="extended bolus",
            top_k=3,
        )
        
        print(f"✓ Found {len(results2)} chunks:")
        for i, result in enumerate(results2, 1):
            print(f"\n  Chunk {i}:")
            print(f"    Source: {result.source}")
            print(f"    Confidence: {result.confidence:.2f}")
            print(f"    Quote: {result.quote[:100]}...")
        
        if len(results) == 0 and len(results2) == 0:
            print("\n⚠️  WARNING: No meal-related features found in knowledge base")
            print("   This may cause generic responses instead of device-specific advice")
            return False
        
        return True
    except ImportError:
        print("\n⚠️  ChromaDB researcher not available, skipping knowledge base check")
        return None
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}", exc_info=True)
        print(f"\n✗ Error: {e}")
        return False


def main():
    """Run all debug tests."""
    print("\n" + "█"*80)
    print("MEAL MANAGEMENT QUERY DEBUG SCRIPT")
    print("█"*80)
    
    try:
        # Test 1: Triage detection
        classification = test_triage_detection()
        
        # Test 2: Unified agent recognition
        is_meal, food = test_unified_agent_recognition()
        
        # Test 3: Full response generation
        response, sources = test_full_response_generation()
        
        # Test 4: Response validation
        if response:
            criteria = validate_response_criteria(response)
        
        # Test 5: Knowledge base verification
        kb_result = search_knowledge_base()
        
        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        
        print(f"\n✓ Triage Detection: {'PASS' if classification.confidence >= 0.7 else 'FAIL'}")
        print(f"✓ Unified Recognition: {'PASS' if is_meal else 'FAIL'}")
        print(f"✓ Response Generated: {'PASS' if response else 'FAIL'}")
        if response:
            pass_rate = (sum(1 for v in criteria.values() if v) / len(criteria)) * 100
            print(f"✓ Response Quality: {'PASS' if pass_rate >= 80 else 'FAIL'} ({pass_rate:.0f}%)")
        print(f"✓ Knowledge Base: {'PASS' if kb_result else 'NEEDS_ATTENTION' if kb_result is None else 'FAIL'}")
        
        print("\n" + "█"*80)
        print("DEBUG COMPLETE")
        print("█"*80 + "\n")
        
    except Exception as e:
        logger.error(f"Fatal error in debug script: {e}", exc_info=True)
        print(f"\n✗ FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
