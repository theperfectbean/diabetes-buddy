#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.unified_agent import UnifiedAgent

print("="*70)
print("DIABETES BUDDY - PRODUCT-AGNOSTIC RESPONSE TEST")
print("="*70)

agent = UnifiedAgent(project_root=str(PROJECT_ROOT))
query = "How should I manage dawn phenomenon?"

print(f"\nQUERY: {query}\n")
print("-"*70)

result = agent.process(query)

print("\nRESPONSE:")
print("="*70)
print(result.answer)
print("="*70)

print("\n\nVALIDATION CHECKS:")
print("-"*70)

response_lower = result.answer.lower()
product_names = ["nightscout", "openaps", "loop", "androidaps", "camaps", "ypsomed", "freestyle", "libre"]
found_products = [p for p in product_names if p in response_lower]

if found_products:
    print(f"❌ FAIL: Found product names: {', '.join(found_products)}")
else:
    print("✅ PASS: No product names found")

if "**Sources" in result.answer or "**sources" in result.answer.lower():
    print("✅ PASS: Sources section found")
else:
    print("❌ FAIL: No Sources section found")

if "[source:" in result.answer.lower() or "[confidence:" in result.answer.lower():
    print("❌ FAIL: Found inline citations")
else:
    print("✅ PASS: No inline citations")

print("-"*70)
print(f"\nMetadata:")
print(f"  Success: {result.success}")
print(f"  Sources used: {len(result.sources_used)}")
