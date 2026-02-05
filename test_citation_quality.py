#!/usr/bin/env python3
"""
Test script to validate citation quality improvements.

Tests 3 validation queries:
1. Algorithm Query: "How does autosens work in OpenAPS?"
2. Clinical Query: "What is dawn phenomenon and how do I manage it?"
3. Device Query: "How do I change my basal rate on my pump?"

Validates minimum 3 citations per response and logs results.
"""

import sys
import time
from pathlib import Path
import csv
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Activate venv first
import os
os.environ['PYTHONPATH'] = str(project_root)

from agents.unified_agent import UnifiedAgent


def count_citations(response: str) -> int:
    """Count citations in response using regex patterns."""
    import re
    citation_pattern = r'\[\d+\]|\[Glooko\]|\[[\w\s]+\]'
    citations = re.findall(citation_pattern, response)
    return len(citations)


def test_query(agent: UnifiedAgent, query: str, test_name: str) -> dict:
    """Test a single query and validate citations."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"{'='*70}")
    print(f"Query: {query}\n")
    
    start_time = time.time()
    
    try:
        # Process query
        response = agent.process(query=query)
        elapsed = time.time() - start_time
        
        if not response.success:
            print(f"❌ FAILED: Response was not successful")
            return {
                "test_name": test_name,
                "query": query,
                "success": False,
                "error": "Response not successful",
                "citation_count": 0,
                "response_length": 0,
                "elapsed": elapsed
            }
        
        answer = response.answer
        citation_count = count_citations(answer)
        response_length = len(answer)
        
        # Validate minimum 3 citations
        passes = citation_count >= 3
        status = "✅ PASS" if passes else "⚠️ LOW CITATIONS"
        
        print(f"Response Length: {response_length} chars")
        print(f"Citation Count: {citation_count} {status}")
        print(f"Execution Time: {elapsed:.2f}s")
        print(f"\n--- Response Preview ---\n{answer[:500]}...\n" if len(answer) > 500 else f"\n--- Full Response ---\n{answer}\n")
        
        return {
            "test_name": test_name,
            "query": query,
            "success": True,
            "citation_count": citation_count,
            "passes_threshold": passes,
            "response_length": response_length,
            "elapsed": elapsed
        }
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "test_name": test_name,
            "query": query,
            "success": False,
            "error": str(e),
            "citation_count": 0,
            "response_length": 0,
            "elapsed": time.time() - start_time
        }


def main():
    """Run citation quality tests."""
    print("\n" + "="*70)
    print("CITATION QUALITY VALIDATION TEST")
    print("="*70)
    print("Testing citation improvements in Diabetes Buddy responses")
    print("Minimum threshold: 3 citations per response")
    
    # Initialize agent
    try:
        agent = UnifiedAgent(project_root=str(project_root))
        print("\n✅ UnifiedAgent initialized successfully")
    except Exception as e:
        print(f"\n❌ Failed to initialize agent: {e}")
        sys.exit(1)
    
    # Define test queries
    test_cases = [
        (
            "How does autosens work in OpenAPS?",
            "Algorithm Query"
        ),
        (
            "What is dawn phenomenon and how do I manage it?",
            "Clinical Query"
        ),
        (
            "How do I change my basal rate on my pump?",
            "Device Query"
        ),
    ]
    
    # Run tests
    results = []
    for query, test_name in test_cases:
        result = test_query(agent, query, test_name)
        results.append(result)
        time.sleep(1)  # Rate limit between queries
    
    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")
    
    passed = sum(1 for r in results if r.get('passes_threshold', False))
    total = len(results)
    successful = sum(1 for r in results if r.get('success', False))
    
    print(f"Tests Completed: {successful}/{total}")
    print(f"Citation Threshold Met: {passed}/{total}")
    
    # Log results to CSV
    csv_path = project_root / "data" / "citation_quality_test_results.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'timestamp', 'test_name', 'query', 'success', 'citation_count', 
            'passes_threshold', 'response_length', 'elapsed'
        ])
        writer.writeheader()
        for result in results:
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'test_name': result.get('test_name', ''),
                'query': result.get('query', '')[:100],
                'success': result.get('success', False),
                'citation_count': result.get('citation_count', 0),
                'passes_threshold': result.get('passes_threshold', False),
                'response_length': result.get('response_length', 0),
                'elapsed': result.get('elapsed', 0)
            })
    
    print(f"\n📊 Results logged to: {csv_path}")
    
    # Exit code based on results
    if passed == total and successful == total:
        print("\n✅ ALL TESTS PASSED!\n")
        return 0
    else:
        print(f"\n⚠️  {total - passed} tests did not meet citation threshold\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
