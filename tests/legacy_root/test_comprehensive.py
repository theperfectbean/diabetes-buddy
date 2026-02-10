#!/usr/bin/env python3
"""
FINAL COMPREHENSIVE VALIDATION TEST
Verifies all fixes for device-aware query processing
"""
from agents.unified_agent import UnifiedAgent
import logging

# Minimal logging
logging.basicConfig(level=logging.ERROR)

print("\n" + "=" * 80)
print("COMPREHENSIVE DEVICE-AWARE SYSTEM VALIDATION")
print("=" * 80)

agent = UnifiedAgent()

# TEST 1: Device Detection
print("\n[TEST 1] Device Detection")
print("-" * 80)
devices = agent.source_manager.get_user_devices() if agent.source_manager else []
print(f"✓ Detected {len(devices)} devices:")
for d in devices:
    print(f"  • {d['name']} ({d['type']})")

# Verify CamAPS FX is first
assert devices and devices[0]['name'] == 'CamAPS FX', "❌ CamAPS FX should be first device"
print("✓ CamAPS FX correctly identified as primary device")

# TEST 2: Knowledge Base Search
print("\n[TEST 2] Knowledge Base Search")
print("-" * 80)
query = "how do i mitigate my highs?"
results = agent.researcher.query_knowledge(query, top_k=10)

print(f"✓ Retrieved {len(results)} results")
device_results = [r for r in results if any(d in r.source.lower() for d in ['camaps', 'ypsomed', 'libre'])]
print(f"✓ {len(device_results)} results from device manuals")

# Verify device results have high confidence
top_device = device_results[0] if device_results else None
if top_device:
    print(f"✓ Top device result: {top_device.source} ({top_device.confidence:.1%} confidence)")
    assert top_device.confidence >= 0.95, "❌ Device results should have 95%+ confidence after boost"
    print("✓ Confidence boost applied correctly (95%+)")

# Verify CamAPS content
camaps_results = [r for r in results[:5] if 'camaps' in r.source.lower()]
if camaps_results:
    print(f"✓ CamAPS manual appears in top 5 results")
    if 'boost' in camaps_results[0].quote.lower():
        print("✓ CamAPS chunk contains 'Boost' feature")

# TEST 3: Full Query Processing
print("\n[TEST 3] Full Query Processing")
print("-" * 80)
response = agent.process(query)

print(f"✓ Query processed successfully: {response.success}")
print(f"✓ Sources used: {', '.join(response.sources_used)}")

# TEST 4: Device-Specific Response Content
print("\n[TEST 4] Response Content Analysis")
print("-" * 80)
answer_lower = response.answer.lower()

required_terms = ['camaps', 'boost']
found_required = [t for t in required_terms if t in answer_lower]
print(f"✓ Required device terms found: {found_required}")

forbidden_terms = ['some systems', 'most pumps', 'insulin pumps can']
found_forbidden = [t for t in forbidden_terms if t in answer_lower]
if found_forbidden:
    print(f"⚠ Generic terms found: {found_forbidden}")
else:
    print("✓ No forbidden generic terms found")

# Verify "your CamAPS FX" phrase
if 'your camaps' in answer_lower:
    print("✓ Uses personalized device reference ('your CamAPS FX')")
else:
    print("⚠ Missing personalized device reference")

# TEST 5: Response Quality
print("\n[TEST 5] Response Quality")
print("-" * 80)
paragraphs = [p for p in response.answer.split('\n\n') if p.strip()]
print(f"✓ Response has {len(paragraphs)} paragraphs")
print(f"✓ Total length: {len(response.answer)} characters")

# Show first paragraph
print("\nFirst paragraph:")
print(f"  {paragraphs[0][:200]}...")

# FINAL VERDICT
print("\n" + "=" * 80)
print("FINAL VALIDATION RESULTS")
print("=" * 80)

all_pass = (
    len(devices) > 0 and
    devices[0]['name'] == 'CamAPS FX' and
    len(device_results) > 0 and
    top_device and top_device.confidence >= 0.95 and
    response.success and
    all(t in answer_lower for t in required_terms) and
    len(found_forbidden) == 0
)

if all_pass:
    print("✅ ALL TESTS PASSED - DEVICE-AWARE SYSTEM FULLY OPERATIONAL")
    print("\nKey Achievements:")
    print("  ✓ CamAPS FX detected as primary device")
    print("  ✓ CamAPS manual chunks boosted to 95%+ confidence")
    print("  ✓ Response uses device-specific language (Boost, CamAPS FX)")
    print("  ✓ No generic pump terminology")
else:
    print("⚠ SOME TESTS FAILED - Review details above")

print("=" * 80 + "\n")
