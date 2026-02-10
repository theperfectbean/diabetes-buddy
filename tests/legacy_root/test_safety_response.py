#!/usr/bin/env python3
"""Test what's triggering the safety filter"""

import re

response_text = """It sounds like you're looking for ways to manage high blood sugar levels, or hyperglycemia. That's a really important aspect of diabetes management!

First and foremost, if you suspect your blood glucose is high, the immediate steps are to check your blood glucose more frequently over the next few hours and then work with your doctor or diabetes advisor to adapt your insulin delivery settings to the changed conditions. If you're ever uncertain, it's always best to contact your healthcare team right away."""

UNITS_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(u|units?)\b", re.IGNORECASE)

print("Testing UNITS_PATTERN:")
matches = UNITS_PATTERN.findall(response_text)
if matches:
    print(f"  MATCHED: {matches}")
else:
    print("  No matches")

# Check what the actual safety classifier sees
from agents.safety_tiers import SafetyTierClassifier

classifier = SafetyTierClassifier()

print("\nChecking _contains_specific_units():")
result = classifier._contains_specific_units(response_text)
print(f"  Result: {result}")

# Full classification
print("\nFull classification:")
decision = classifier.classify(
    query="how do i mitigate my highs?",
    response_text=response_text,
    sources_used=["australian_guidelines"],
    rag_quality={"confidence": 0.68},
    glooko_available=False
)

print(f"  Tier: {decision.tier.value}")
print(f"  Action: {decision.action.value}")  
print(f"  Reason: {decision.reason}")
