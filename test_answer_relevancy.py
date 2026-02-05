"""
Test answer relevancy improvements.

Validates that responses:
1. Directly address the specific question asked
2. Include key query terms in the response
3. Achieve minimum keyword overlap threshold (60%)
"""

import os
import sys
from pathlib import Path
import csv
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.unified_agent import UnifiedAgent


def extract_keywords(query: str) -> list:
    """Extract key terms from query for validation."""
    import re
    
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "how", "what", "when", "where", "why", "who", "which", "do", "does", 
        "did", "can", "could", "should", "would", "will", "i", "my", "me",
        "in", "on", "at", "to", "from", "by", "with", "about", "for", "of"
    }
    
    query_lower = query.lower()
    query_words = re.findall(r'\b[a-z]{2,}\b', query_lower)
    key_terms = [w for w in query_words if w not in stopwords]
    
    return key_terms


def calculate_keyword_overlap(query: str, response: str) -> dict:
    """Calculate keyword overlap between query and response."""
    key_terms = extract_keywords(query)
    
    if not key_terms:
        return {
            "overlap": 1.0,
            "matched": [],
            "missing": [],
            "total_keywords": 0
        }
    
    response_lower = response.lower()
    matched = [term for term in key_terms if term in response_lower]
    missing = [term for term in key_terms if term not in response_lower]
    
    overlap = len(matched) / len(key_terms)
    
    return {
        "overlap": overlap,
        "matched": matched,
        "missing": missing,
        "total_keywords": len(key_terms)
    }


def test_answer_relevancy():
    """Test answer relevancy with 3 validation queries."""
    print("=" * 70)
    print("ANSWER RELEVANCY TEST")
    print("=" * 70)
    print()
    
    # Initialize agent
    agent = UnifiedAgent()
    
    # Test queries with expected keywords
    test_queries = [
        {
            "query": "How do I extend my sensor session?",
            "expected_keywords": ["extend", "sensor", "session"],
            "description": "Configuration query - sensor extension"
        },
        {
            "query": "Why does my algorithm keep suspending insulin?",
            "expected_keywords": ["suspend", "algorithm", "insulin"],
            "description": "Troubleshooting query - insulin suspension"
        },
        {
            "query": "What's the difference between manual and auto mode?",
            "expected_keywords": ["manual", "auto", "mode", "difference"],
            "description": "Comparison query - manual vs auto mode"
        }
    ]
    
    results = []
    passing_tests = 0
    min_overlap_threshold = 0.6  # 60% keyword overlap required
    
    for i, test_case in enumerate(test_queries, 1):
        query = test_case["query"]
        description = test_case["description"]
        expected = test_case["expected_keywords"]
        
        print(f"\nTest {i}/3: {description}")
        print(f"Query: \"{query}\"")
        print(f"Expected keywords: {', '.join(expected)}")
        print("-" * 70)
        
        # Process query
        try:
            response = agent.process(query)
            answer = response.answer
            
            # Calculate keyword overlap
            overlap_result = calculate_keyword_overlap(query, answer)
            overlap_pct = overlap_result["overlap"]
            matched = overlap_result["matched"]
            missing = overlap_result["missing"]
            
            # Determine pass/fail
            passed = overlap_pct >= min_overlap_threshold
            passing_tests += (1 if passed else 0)
            
            # Display results
            print(f"✓ Response generated ({len(answer)} chars)")
            print(f"  Keyword overlap: {overlap_pct:.1%} ({len(matched)}/{len(matched) + len(missing)} keywords)")
            print(f"  Matched keywords: {', '.join(matched) if matched else 'none'}")
            if missing:
                print(f"  Missing keywords: {', '.join(missing)}")
            
            # Pass/fail indicator
            if passed:
                print(f"  ✅ PASS - Overlap {overlap_pct:.1%} >= {min_overlap_threshold:.0%}")
            else:
                print(f"  ❌ FAIL - Overlap {overlap_pct:.1%} < {min_overlap_threshold:.0%}")
            
            # Preview response
            print(f"\n  Response preview:")
            print(f"  {answer[:300]}{'...' if len(answer) > 300 else ''}")
            
            # Store results
            results.append({
                "test_name": description,
                "query": query,
                "overlap_percentage": overlap_pct,
                "matched_keywords": len(matched),
                "missing_keywords": len(missing),
                "passed": passed,
                "response_length": len(answer)
            })
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append({
                "test_name": description,
                "query": query,
                "overlap_percentage": 0.0,
                "matched_keywords": 0,
                "missing_keywords": len(expected),
                "passed": False,
                "response_length": 0
            })
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests passed: {passing_tests}/{len(test_queries)}")
    print(f"Pass rate: {passing_tests/len(test_queries):.1%}")
    
    # Save results to CSV
    csv_path = project_root / "data" / "answer_relevancy_test_results.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'timestamp', 'test_name', 'query', 'overlap_percentage',
            'matched_keywords', 'missing_keywords', 'passed', 'response_length'
        ])
        writer.writeheader()
        
        for result in results:
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                **result
            })
    
    print(f"\nResults saved to: {csv_path}")
    
    # Overall verdict
    if passing_tests == len(test_queries):
        print("\n✅ ALL TESTS PASSED - Answer relevancy improvements validated")
        return 0
    else:
        print(f"\n⚠️  {len(test_queries) - passing_tests} TEST(S) FAILED - Further refinement needed")
        return 1


if __name__ == "__main__":
    exit_code = test_answer_relevancy()
    sys.exit(exit_code)
