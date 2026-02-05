#!/usr/bin/env python3
"""Test the web API with 'how do i mitigate my highs?' query"""

import requests
import json

url = "http://localhost:8000/api/query"
query = "how do i mitigate my highs?"

print(f"Testing query: '{query}'")
print("=" * 80)

response = requests.post(
    url,
    json={"query": query},
    headers={"Content-Type": "application/json"}
)

print(f"Status: {response.status_code}")
print()

if response.status_code == 200:
    data = response.json()
    print(f"Classification: {data.get('classification')}")
    print(f"Severity: {data.get('severity')}")
    print(f"Confidence: {data.get('confidence')}")
    print()
    print("Answer:")
    print("-" * 80)
    answer = data.get('answer', '')
    # Check for key terms
    print(answer)
    print("-" * 80)
    print()
    
    # Check for device-specific content
    camaps_count = answer.lower().count('camaps')
    boost_count = answer.lower().count('boost')
    
    print(f"✓ CamAPS mentions: {camaps_count}")
    print(f"✓ Boost mentions: {boost_count}")
    
    # Check for forbidden generic terms
    if 'basal adjustment' in answer.lower():
        print(f"✗ WARNING: Contains 'basal adjustment' (should be device-specific)")
    if 'pre-bolus' in answer.lower():
        print(f"✗ WARNING: Contains 'pre-bolus' (should be device-specific)")
        
    # Check for block message
    if "I can't help with that" in answer:
        print(f"✗ ERROR: Safety filter blocking query!")
    else:
        print(f"✓ No safety block")
        
    print()
    print(f"Sources returned: {len(data.get('sources', []))}")
    for i, source in enumerate(data.get('sources', [])[:3]):
        print(f"  {i+1}. {source.get('source')} (confidence: {source.get('confidence')})")
else:
    print(f"Error: {response.text}")
