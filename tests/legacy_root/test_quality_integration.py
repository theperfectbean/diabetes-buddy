"""
Quick integration test for automated response quality evaluation.

Tests Phase 1-3 features:
- Quality evaluation framework
- Hallucination detection
- Feedback learning loop
"""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_quality_evaluator_import():
    """Test that quality evaluator can be imported."""
    from agents.response_quality_evaluator import ResponseQualityEvaluator, QualityScore
    print("✓ Quality evaluator imports successfully")


def test_quality_evaluator_initialization():
    """Test quality evaluator initializes with config."""
    from agents.response_quality_evaluator import ResponseQualityEvaluator
    
    config = {
        'enabled': True,
        'cache_enabled': True,
        'log_path': 'data/test_quality_scores.csv'
    }
    
    evaluator = ResponseQualityEvaluator(config=config)
    assert evaluator is not None
    assert evaluator.config == config
    print("✓ Quality evaluator initializes correctly")


def test_hallucination_detection_import():
    """Test hallucination detection imports."""
    from agents.safety import HallucinationFinding, HybridAuditResult
    print("✓ Hallucination detection imports successfully")


def test_personalization_learning():
    """Test personalization manager feedback learning."""
    from agents.device_personalization import PersonalizationManager
    
    pm = PersonalizationManager()
    assert hasattr(pm, 'learn_from_negative_feedback')
    assert hasattr(pm, 'adjust_retrieval_strategy')
    print("✓ Personalization manager has learning methods")


def test_unified_agent_with_quality():
    """Test UnifiedAgent initializes with quality evaluator."""
    from agents.unified_agent import UnifiedAgent
    
    agent = UnifiedAgent()
    assert hasattr(agent, 'quality_evaluator')
    print(f"✓ UnifiedAgent with quality evaluator: enabled={agent.quality_evaluator is not None}")


def test_config_loading():
    """Test that hybrid_knowledge.yaml has quality evaluation config."""
    import yaml
    from pathlib import Path
    
    # Try multiple possible locations
    possible_paths = [
        Path(__file__).parent.parent / "config" / "hybrid_knowledge.yaml",
        Path(__file__).parent / "config" / "hybrid_knowledge.yaml",
        Path("config/hybrid_knowledge.yaml"),
    ]
    
    config_path = None
    for path in possible_paths:
        if path.exists():
            config_path = path
            break
    
    if not config_path:
        print(f"⚠️  Could not find config file, tried: {[str(p) for p in possible_paths]}")
        return
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    assert 'quality_evaluation' in config
    assert config['quality_evaluation']['enabled'] is True
    assert 'hallucination_detection' in config
    print("✓ Configuration has quality evaluation and hallucination detection")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Quality Evaluation Implementation")
    print("=" * 60)
    
    try:
        test_quality_evaluator_import()
        test_quality_evaluator_initialization()
        test_hallucination_detection_import()
        test_personalization_learning()
        test_unified_agent_with_quality()
        test_config_loading()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
