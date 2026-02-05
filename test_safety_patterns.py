#!/usr/bin/env python3
"""Test that DANGEROUS_PATTERNS still catch actual dangerous advice"""

import re
from agents.safety_tiers import SafetyTierClassifier

classifier = SafetyTierClassifier()

# Test cases
test_cases = [
    ("Educational (should PASS)", "it can stop your insulin delivery and lead to hyperglycemia"),
    ("Educational (should PASS)", "If insulin delivery stops, your glucose will rise"),
    ("Dangerous (should BLOCK)", "You should stop your insulin"),
    ("Dangerous (should BLOCK)", "Please discontinue your medication"),
    ("Dangerous (should BLOCK)", "skip your insulin doses"),
    ("Dangerous (should BLOCK)", "don't take your insulin"),
]

print("Testing DANGEROUS_PATTERNS:")
print("=" * 80)

for label, text in test_cases:
    matched = False
    for pattern in classifier.DANGEROUS_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matched = True
            break
    
    status = "✗ BLOCKED" if matched else "✓ ALLOWED"
    expected = "BLOCK" in label
    correct = (matched == expected)
    
    result = "✓ CORRECT" if correct else "❌ WRONG"
    print(f"{result} {status} - {label}")
    print(f"   Text: '{text}'")
    if matched:
        print(f"   Matched: {match.group(0)}")
    print()
