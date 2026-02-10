#!/usr/bin/env python3
"""Test what safety patterns are triggered by 'how do i mitigate my highs?'"""

import re
from agents.safety_tiers import SafetyTierClassifier

# Create classifier
classifier = SafetyTierClassifier()

# Test query
query = "how do i mitigate my highs?"
query_lower = query.lower()

print(f"Testing query: '{query}'")
print("=" * 80)

# Check each pattern category
print("\n1. EDUCATIONAL_STRATEGY_PATTERNS (should match - ALLOW):")
for pattern in classifier.EDUCATIONAL_STRATEGY_PATTERNS:
    match = re.search(pattern, query_lower, re.IGNORECASE)
    if match:
        print(f"  ✓ MATCHED: {pattern}")
        print(f"    Match text: '{match.group(0)}'")

print("\n2. DOSING_REQUEST_PATTERNS (should NOT match):")
for pattern in classifier.DOSING_REQUEST_PATTERNS:
    match = re.search(pattern, query_lower, re.IGNORECASE)
    if match:
        print(f"  ✗ MATCHED: {pattern}")
        print(f"    Match text: '{match.group(0)}'")
    
print("\n3. DANGEROUS_PATTERNS (should NOT match):")
for pattern in classifier.DANGEROUS_PATTERNS:
    match = re.search(pattern, query_lower, re.IGNORECASE)
    if match:
        print(f"  ✗ MATCHED: {pattern}")
        print(f"    Match text: '{match.group(0)}'")

print("\n4. CLINICAL_DECISION_PATTERNS (should NOT match):")
for pattern in classifier.CLINICAL_DECISION_PATTERNS:
    match = re.search(pattern, query_lower, re.IGNORECASE)
    if match:
        print(f"  ✗ MATCHED: {pattern}")
        print(f"    Match text: '{match.group(0)}'")

# Now run full classification with a dummy response
dummy_response = "Try using the Boost feature on your CamAPS FX pump to increase insulin delivery."

print("\n" + "=" * 80)
print("FULL CLASSIFICATION TEST:")
print(f"Query: '{query}'")
print(f"Response: '{dummy_response}'")
print("=" * 80)

decision = classifier.classify(
    query=query,
    response_text=dummy_response,
    sources_used=["user_manual_fx"],
    rag_quality={"confidence": 1.0, "chunk_count": 5},
    glooko_available=False
)

print(f"\nResult:")
print(f"  Tier: {decision.tier.value}")
print(f"  Action: {decision.action.value}")
print(f"  Reason: {decision.reason}")
if decision.override_response:
    print(f"  Override response: {decision.override_response[:100]}...")
