from agents.triage import TriageAgent

triage = TriageAgent()
response = triage.process("What is Ease-off mode in CamAPS?")

print("\n" + "="*60)
print("SEARCH RESULTS WITH METADATA")
print("="*60)

for source_key, results in response.results.items():
    print(f"\n{source_key}: {len(results)} results")
    for i, result in enumerate(results[:3], 1):
        print(f"\n  Result {i}:")
        print(f"    Confidence: {result.confidence}")
        print(f"    Source: {result.source}")
        print(f"    Page: {result.page_number}")
        print(f"    Quote: {result.quote[:100]}...")
        print(f"    Context: {result.context}")

print("\n" + "="*60)
print("SYNTHESIZED ANSWER")
print("="*60)
print(response.synthesized_answer[:500])
