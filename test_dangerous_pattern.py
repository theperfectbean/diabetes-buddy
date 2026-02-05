#!/usr/bin/env python3
"""Test what DANGEROUS_PATTERNS match in the response"""

import re
from agents.safety_tiers import SafetyTierClassifier

response = """If an alarm, especially an occlusion alarm, isn't dealt with, it can stop your insulin delivery and lead to hyperglycemia."""

classifier = SafetyTierClassifier()

print(f"Testing text: '{response}'")
print("=" * 80)

print("\nDANGEROUS_PATTERNS:")
for pattern in classifier.DANGEROUS_PATTERNS:
    match = re.search(pattern, response, re.IGNORECASE)
    if match:
        print(f"  ✗ MATCHED: {pattern}")
        print(f"    Match text: '{match.group(0)}'")
