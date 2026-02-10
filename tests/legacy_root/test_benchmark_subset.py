#!/usr/bin/env python3
"""
Benchmark subset test - run 10 queries to measure source_integration improvement.

Tests with citation enforcement enabled to measure improvement from baseline (2.52/5.0).
"""

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.unified_agent import UnifiedAgent
from agents.response_quality_evaluator import ResponseQualityEvaluator
import csv
from datetime import datetime


# Test queries (mixed categories)
TEST_QUERIES = [
    "How does autosens work in OpenAPS?",
    "What is dawn phenomenon and how do I manage it?",
    "How do I change my basal rate on my pump?",
    "What's the difference between time-in-range and A1C?",
    "How can I detect hypoglycemia patterns in my data?",
    "What are the FDA-approved CGM systems?",
    "How do I calculate insulin to carb ratio?",
    "What are common causes of high blood glucose at night?",
    "How do I prepare for exercise with diabetes?",
    "What should I know about sick day management?",
]


def run_benchmark_subset():
    """Run 10-query benchmark with citation enforcement."""
    print("\n" + "="*70)
    print("BENCHMARK SUBSET TEST - SOURCE INTEGRATION MEASUREMENT")
    print("="*70)
    print(f"Running {len(TEST_QUERIES)} queries to measure citation/source integration improvements")
    print("Baseline (before): 2.52/5.0")
    print("Target (after): 3.5+/5.0\n")
    
    # Initialize agent and evaluator
    try:
        agent = UnifiedAgent(project_root=str(project_root))
        evaluator = ResponseQualityEvaluator()
        print("✅ Agents initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        sys.exit(1)
    
    # Run queries and collect quality scores
    results = []
    csv_path = project_root / "data" / "benchmark_subset_results.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'timestamp', 'query', 'answer_relevancy', 'practical_helpfulness',
            'knowledge_guidance', 'tone_professionalism', 'clarity_structure',
            'source_integration', 'average_score', 'citation_count'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for i, query in enumerate(TEST_QUERIES, 1):
            print(f"[{i}/{len(TEST_QUERIES)}] Query: {query[:60]}...")
            
            try:
                start = time.time()
                response = agent.process(query=query)
                elapsed = time.time() - start
                
                if not response.success:
                    print(f"  ❌ Response failed")
                    continue
                
                # Evaluate quality
                try:
                    scores = evaluator.evaluate(query, response.answer)
                    
                    # Count citations
                    import re
                    citation_pattern = r'\[\d+\]|\[Glooko\]|\[[\w\s]+\]'
                    citations = re.findall(citation_pattern, response.answer)
                    citation_count = len(citations)
                    
                    avg_score = (
                        scores.get('answer_relevancy', 0) +
                        scores.get('practical_helpfulness', 0) +
                        scores.get('knowledge_guidance', 0) +
                        scores.get('tone_professionalism', 0) +
                        scores.get('clarity_structure', 0) +
                        scores.get('source_integration', 0)
                    ) / 6
                    
                    print(f"  ✓ source_integration: {scores.get('source_integration', 0):.2f}/5.0, citations: {citation_count}")
                    
                    # Write to CSV
                    writer.writerow({
                        'timestamp': datetime.now().isoformat(),
                        'query': query,
                        'answer_relevancy': scores.get('answer_relevancy', 0),
                        'practical_helpfulness': scores.get('practical_helpfulness', 0),
                        'knowledge_guidance': scores.get('knowledge_guidance', 0),
                        'tone_professionalism': scores.get('tone_professionalism', 0),
                        'clarity_structure': scores.get('clarity_structure', 0),
                        'source_integration': scores.get('source_integration', 0),
                        'average_score': avg_score,
                        'citation_count': citation_count
                    })
                    csvfile.flush()
                    
                    results.append({
                        'query': query,
                        'scores': scores,
                        'citations': citation_count
                    })
                    
                except Exception as e:
                    print(f"  ⚠️ Quality evaluation failed: {e}")
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
            
            time.sleep(2)  # Rate limiting
    
    # Summary
    print("\n" + "="*70)
    print("BENCHMARK RESULTS SUMMARY")
    print("="*70)
    
    if results:
        source_integration_scores = [
            r['scores'].get('source_integration', 0) for r in results
        ]
        avg_source_integration = sum(source_integration_scores) / len(source_integration_scores)
        avg_citations = sum(r['citations'] for r in results) / len(results)
        
        print(f"Queries Tested: {len(results)}/{len(TEST_QUERIES)}")
        print(f"Average Source Integration Score: {avg_source_integration:.2f}/5.0")
        print(f"Baseline (before): 2.52/5.0")
        print(f"Improvement: {avg_source_integration - 2.52:.2f} points")
        print(f"Target Met: {'✅ YES' if avg_source_integration >= 3.5 else '⚠️ NO - Needs refinement'}")
        print(f"\nAverage Citations per Response: {avg_citations:.1f}")
        print(f"Citation Minimum Target: 3.0")
        
        print(f"\n📊 Results saved to: {csv_path}")
    else:
        print("❌ No results collected - check for errors above")
        return 1
    
    return 0 if avg_source_integration >= 3.5 else 1


if __name__ == "__main__":
    sys.exit(run_benchmark_subset())
