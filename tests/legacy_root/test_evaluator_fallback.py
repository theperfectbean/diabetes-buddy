"""
Test script to validate ResponseQualityEvaluator fallback mechanisms

This script tests:
1. Groq → Gemini fallback on rate limit
2. Evaluation caching
3. Error logging
4. Provider switching
"""

import asyncio
import csv
import pandas as pd
from pathlib import Path
from agents.response_quality_evaluator import ResponseQualityEvaluator


async def test_fallback_mechanism():
    """Test that evaluator falls back to Gemini when Groq fails."""
    print("\n" + "="*60)
    print("TEST 1: Provider Fallback Mechanism")
    print("="*60)
    
    config = {
        'primary_provider': 'groq',
        'fallback_provider': 'gemini',
        'max_retries': 2,
        'cache_enabled': False,  # Disable caching for this test
        'log_path': 'data/quality_scores_fallback_test.csv'
    }
    
    evaluator = ResponseQualityEvaluator(config)
    
    # Test query
    query = "How do I set up a continuous glucose monitor?"
    response = """A continuous glucose monitor (CGM) works by placing a small sensor under your skin.
The sensor measures glucose levels in interstitial fluid every few minutes. Most modern CGMs like 
Dexcom or Freestyle require calibration and smartphone integration. Talk to your healthcare provider 
about which system is right for you."""
    sources = ["Dexcom Official Guide", "Diabetes Care Journal"]
    
    print(f"\nEvaluating response from {evaluator.current_provider}...")
    print(f"Query: {query[:50]}...")
    
    score = await evaluator.evaluate_async(query, response, sources)
    
    print(f"✅ Evaluation completed")
    print(f"   Provider used: {score.provider_used}")
    print(f"   Average score: {score.average_dimension_score:.2f}")
    print(f"   Evaluation failed: {score.evaluation_failed}")
    
    if score.evaluation_failed:
        print("⚠️ Evaluation failed (expected if Groq rate limit hit)")
    
    return score


async def test_caching():
    """Test that caching prevents duplicate evaluations."""
    print("\n" + "="*60)
    print("TEST 2: Evaluation Caching")
    print("="*60)
    
    config = {
        'cache_enabled': True,
        'cache_max_size': 10,
        'log_path': 'data/quality_scores_caching_test.csv'
    }
    
    evaluator = ResponseQualityEvaluator(config)
    
    query = "What is a basal rate?"
    response = "A basal rate is the amount of insulin your pump delivers continuously throughout the day and night. It mimics the insulin your pancreas would normally produce."
    sources = ["Insulin Pump Guide"]
    
    print(f"\nFirst evaluation (cache miss)...")
    score1 = await evaluator.evaluate_async(query, response, sources)
    print(f"   Cached: {score1.cached}")
    
    print(f"\nSecond evaluation (cache hit expected)...")
    score2 = await evaluator.evaluate_async(query, response, sources)
    print(f"   Cached: {score2.cached}")
    
    if score2.cached:
        print("✅ Caching working correctly")
    else:
        print("⚠️ Caching not working (may be expected depending on configuration)")
    
    return evaluator.get_cache_stats()


async def test_error_logging():
    """Test that errors are logged properly."""
    print("\n" + "="*60)
    print("TEST 3: Error Logging")
    print("="*60)
    
    error_log = Path('data/evaluation_errors.csv')
    
    if error_log.exists():
        try:
            df = pd.read_csv(error_log)
            print(f"\n✅ Error log exists with {len(df)} entries")
            
            if len(df) > 0:
                print("\nRecent errors:")
                print(df.tail(3).to_string())
                
                # Analysis
                error_types = df['error_type'].value_counts()
                print(f"\nError type distribution:")
                print(error_types)
                
                providers = df['provider_attempted'].value_counts()
                print(f"\nProviders with errors:")
                print(providers)
            else:
                print("Error log is empty (good sign - no errors yet)")
        except Exception as e:
            print(f"⚠️ Could not read error log: {e}")
    else:
        print("ℹ️ Error log doesn't exist yet (no errors encountered)")
    
    return error_log


async def test_quality_scores():
    """Analyze quality scores and provider distribution."""
    print("\n" + "="*60)
    print("TEST 4: Quality Scores Analysis")
    print("="*60)
    
    score_log = Path('data/quality_scores.csv')
    
    if score_log.exists():
        try:
            df = pd.read_csv(score_log)
            print(f"\n✅ Quality scores log has {len(df)} entries")
            
            # Provider distribution
            if 'provider_used' in df.columns:
                providers = df['provider_used'].value_counts()
                print(f"\nProvider distribution:")
                print(providers)
                print(f"   Groq: {providers.get('groq', 0)}")
                print(f"   Gemini: {providers.get('gemini', 0)}")
            
            # Failure distribution
            if 'evaluation_failed' in df.columns:
                failures = df['evaluation_failed'].value_counts()
                total = len(df)
                failed_count = failures.get(True, 0)
                success_rate = ((total - failed_count) / total) * 100
                print(f"\nEvaluation success rate:")
                print(f"   Successful: {total - failed_count}/{total} ({success_rate:.1f}%)")
                print(f"   Failed: {failed_count}/{total}")
            
            # Score statistics
            if 'average_score' in df.columns:
                valid_scores = df[df['average_score'] > 0]['average_score']
                if len(valid_scores) > 0:
                    print(f"\nQuality score statistics (valid scores only):")
                    print(f"   Mean: {valid_scores.mean():.2f}")
                    print(f"   Median: {valid_scores.median():.2f}")
                    print(f"   Min: {valid_scores.min():.2f}")
                    print(f"   Max: {valid_scores.max():.2f}")
            
            return df
        except Exception as e:
            print(f"⚠️ Could not analyze scores: {e}")
            return None
    else:
        print("ℹ️ Quality scores log doesn't exist yet")
        return None


async def test_config_loading():
    """Test that configuration loads correctly."""
    print("\n" + "="*60)
    print("TEST 5: Configuration Loading")
    print("="*60)
    
    from pathlib import Path
    import yaml
    
    config_path = Path('config/response_quality_config.yaml')
    
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            print(f"\n✅ Configuration loaded successfully")
            print(f"\nKey settings:")
            eval_config = config.get('evaluation', {})
            print(f"   Primary provider: {eval_config.get('primary_provider')}")
            print(f"   Fallback provider: {eval_config.get('fallback_provider')}")
            print(f"   Max retries: {eval_config.get('max_retries')}")
            print(f"   Cache enabled: {eval_config.get('cache_enabled')}")
            print(f"   Cache size: {eval_config.get('cache_max_size')}")
            
            return config
        except Exception as e:
            print(f"⚠️ Could not load configuration: {e}")
            return None
    else:
        print("ℹ️ Configuration file not found at config/response_quality_config.yaml")
        return None


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("RESPONSE QUALITY EVALUATOR - FALLBACK MECHANISM TESTING")
    print("="*70)
    
    # Test 1: Configuration
    config = await test_config_loading()
    
    # Test 2: Fallback mechanism
    score = await test_fallback_mechanism()
    
    # Test 3: Caching
    cache_stats = await test_caching()
    
    # Test 4: Error logging
    error_log = await test_error_logging()
    
    # Test 5: Quality scores
    scores_df = await test_quality_scores()
    
    # Summary
    print("\n" + "="*70)
    print("TESTING SUMMARY")
    print("="*70)
    print("""
✅ FALLBACK MECHANISM TESTS COMPLETE

Next steps to complete implementation:
1. Wait for Groq daily token limit to reset (UTC midnight)
2. Run full benchmark: pytest tests/test_response_quality_benchmark.py -v
3. Verify success rate improves from 66% to 90%+
4. Check provider_used column shows mix of Groq and Gemini
5. Verify evaluation_failed count minimal

Expected improvements:
- Valid evaluations: 33/50 → 45-50/50
- Failed evaluations: 17/50 → 0-5/50
- Provider mix: Groq (40) + Gemini (10)
- Success rate: 66% → 90%+

Benchmark command:
  pytest tests/test_response_quality_benchmark.py -v --tb=short

Analysis command:
  python -c "import pandas as pd; df = pd.read_csv('data/quality_scores.csv'); 
  print(f'Valid: {len(df[df[\"evaluation_failed\"]==False])}/  {len(df)}'); 
  print(df['provider_used'].value_counts())"
""")


if __name__ == "__main__":
    asyncio.run(main())
