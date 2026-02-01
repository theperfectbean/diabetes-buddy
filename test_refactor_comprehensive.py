#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.unified_agent import UnifiedAgent

def validate_response(result, test_name):
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"{'='*70}")
    print(result.answer)
    print(f"\n{'─'*70}")
    
    response_lower = result.answer.lower()
    product_names = ["nightscout", "openaps", "loop", "androidaps", "camaps", "ypsomed", "freestyle", "libre"]
    found_products = [p for p in product_names if p in response_lower]
    
    checks_passed = 0
    checks_total = 3
    
    if found_products:
        print(f"❌ FAIL: Product names: {', '.join(found_products)}")
    else:
        print("✅ PASS: No product names")
        checks_passed += 1
    
    if "**Sources" in result.answer or "### Sources" in result.answer:
        print("✅ PASS: Sources section found")
        checks_passed += 1
    else:
        print("❌ FAIL: No Sources section")
    
    if "[source:" in result.answer.lower() or "[confidence:" in result.answer.lower():
        print("❌ FAIL: Inline citations found")
    else:
        print("✅ PASS: No inline citations")
        checks_passed += 1
    
    print(f"\nScore: {checks_passed}/{checks_total}")
    return checks_passed == checks_total

agent = UnifiedAgent(project_root=str(PROJECT_ROOT))

test_queries = [
    ("Clinical query - dawn phenomenon", "How should I manage dawn phenomenon?"),
    ("Device-specific bait", "How do I configure autosens in my system?"),
    ("Basal rate adjustment", "What are best practices for adjusting basal insulin rates?"),
    ("CGM accuracy", "How accurate are continuous glucose monitors?"),
    ("Insulin dosing SAFETY", "How much insulin should I take for 50g carbs?"),
    ("General diabetes education", "What causes high blood sugar in the morning?"),
]

results = []
for test_name, query in test_queries:
    try:
        result = agent.process(query)
        passed = validate_response(result, f"{test_name}: '{query}'")
        results.append((test_name, passed))
    except Exception as e:
        print(f"\n❌ ERROR in {test_name}: {e}")
        results.append((test_name, False))

print(f"\n\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
for test_name, passed in results:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")

total_passed = sum(1 for _, passed in results if passed)
print(f"\nOverall: {total_passed}/{len(results)} tests passed")
