#!/usr/bin/env python3
"""
Test script to verify device-aware knowledge prioritization.

Expected behavior:
- CamAPS FX documentation should be detected
- Search results should prioritize device manuals
- Response should mention device-specific features (Boost, Ease-off, Personal target)
"""

from agents.unified_agent import UnifiedAgent

def main():
    print("\n" + "="*80)
    print("DEVICE-AWARE KNOWLEDGE PRIORITIZATION TEST")
    print("="*80)
    
    # Initialize agent
    print("\n1️⃣  Initializing UnifiedAgent...")
    agent = UnifiedAgent()
    print("   ✅ Agent initialized")
    
    # Test query about managing highs
    test_query = "help me mitigate highs"
    print(f"\n2️⃣  Testing query: '{test_query}'")
    
    # Process query
    print("\n3️⃣  Processing query (debug logs will appear below)...\n")
    response = agent.process(test_query)
    
    # Analyze results
    print("\n" + "="*80)
    print("TEST RESULTS")
    print("="*80)
    
    print(f"\n✅ Query processed successfully: {response.success}")
    print(f"✅ Sources used: {', '.join(response.sources_used)}")
    
    # Check for device-specific terms
    answer_lower = response.answer.lower()
    device_terms = {
        'camaps': 'camaps' in answer_lower,
        'boost': 'boost' in answer_lower,
        'ease-off': 'ease-off' in answer_lower or 'ease off' in answer_lower,
        'personal glucose target': 'personal glucose target' in answer_lower or 'personal target' in answer_lower,
    }
    
    print(f"\n📋 Device-specific features mentioned:")
    for term, found in device_terms.items():
        status = "✅" if found else "❌"
        print(f"   {status} {term.title()}")
    
    # Print response preview
    print(f"\n📝 Response preview (first 800 characters):")
    print("-" * 80)
    print(response.answer[:800])
    if len(response.answer) > 800:
        print("...")
    print("-" * 80)
    
    # Final verdict
    device_mentions = sum(device_terms.values())
    if device_mentions >= 2:
        print(f"\n✅ TEST PASSED: Response is device-specific ({device_mentions}/4 features mentioned)")
    elif device_mentions >= 1:
        print(f"\n⚠️  TEST PARTIAL: Some device features mentioned ({device_mentions}/4)")
    else:
        print(f"\n❌ TEST FAILED: No device-specific features mentioned")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    main()
