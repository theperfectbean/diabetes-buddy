"""
Minimal trace script for CamAPS FX exercise query
Logs exactly which collections are searched and what results come back
"""
import logging
from agents.triage import TriageAgent

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

# The exact query that's failing
query = "How should I prepare for exercise with CamAPS FX?"

print(f"\n{'='*60}")
print(f"QUERY: {query}")
print(f"{'='*60}\n")

# Instantiate triage agent
triage = TriageAgent()

# Process query
response = triage.process(query, verbose=True)

# Inspect classification
print(f"\n{'='*60}")
print(f"CLASSIFICATION RESULTS")
print(f"{'='*60}")
print(f"Category: {response.classification.category.value}")
print(f"Confidence: {response.classification.confidence}")
print(f"Reasoning: {response.classification.reasoning}")
print(f"Secondary: {[c.value for c in response.classification.secondary_categories]}")

# Inspect which collections were actually searched
print(f"\n{'='*60}")
print(f"COLLECTIONS SEARCHED")
print(f"{'='*60}")
for source_key, results in response.results.items():
    print(f"\n{source_key}:")
    print(f"  - Results returned: {len(results)}")
    if results:
        for i, r in enumerate(results[:3], 1):
            print(f"  - Result {i}: confidence={r.confidence:.2f}, quote={r.quote[:80]}...")
    else:
        print(f"  - NO RESULTS")

# Inspect final answer
print(f"\n{'='*60}")
print(f"SYNTHESIZED ANSWER")
print(f"{'='*60}")
print(response.synthesized_answer[:300])
