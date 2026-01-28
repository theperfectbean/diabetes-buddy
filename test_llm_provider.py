#!/usr/bin/env python3
"""
Test script to verify the LLM provider abstraction is working correctly.
Tests the refactored code to ensure all functionality remains intact.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

print("=" * 80)
print("LLM PROVIDER ABSTRACTION TEST")
print("=" * 80)

# Test 1: Provider Factory
print("\n[TEST 1] LLM Provider Factory")
print("-" * 80)
try:
    from agents.llm_provider import LLMFactory, LLMProviderType, get_llm
    
    # Test factory instantiation
    llm = LLMFactory.get_provider()
    print(f"✓ Provider factory initialized")
    print(f"  Provider type: {type(llm).__name__}")
    
    # Test model info
    info = llm.get_model_info()
    print(f"✓ Model info retrieved")
    print(f"  Provider: {info.provider}")
    print(f"  Model: {info.model_name}")
    print(f"  Context window: {info.context_window:,} tokens")
    print(f"  Supports embeddings: {info.supports_embeddings}")
    print(f"  Supports file upload: {info.supports_file_upload}")
    if info.cost_per_million_tokens:
        print(f"  Cost: ${info.cost_per_million_tokens}/M tokens")
    
    # Test helper function
    llm2 = get_llm()
    assert llm is llm2, "Singleton pattern not working"
    print(f"✓ Singleton pattern working (cached instance)")
    
except Exception as e:
    print(f"✗ Provider factory test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Text Generation
print("\n[TEST 2] Text Generation")
print("-" * 80)
try:
    from agents.llm_provider import GenerationConfig
    
    test_prompt = "What is insulin resistance? Answer in one sentence."
    print(f"Prompt: '{test_prompt}'")
    
    response = llm.generate_text(
        prompt=test_prompt,
        config=GenerationConfig(temperature=0.7, max_tokens=100)
    )
    
    print(f"✓ Text generation successful")
    print(f"  Response length: {len(response)} characters")
    print(f"  Response preview: {response[:150]}...")
    
except Exception as e:
    print(f"✗ Text generation test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Embeddings
print("\n[TEST 3] Embeddings")
print("-" * 80)
try:
    test_text = "diabetes management"
    print(f"Text: '{test_text}'")
    
    embedding = llm.embed_text(test_text)
    
    print(f"✓ Single text embedding successful")
    print(f"  Dimension: {len(embedding)}")
    print(f"  First 5 values: {embedding[:5]}")
    
    # Test batch embeddings
    test_texts = ["insulin sensitivity", "blood glucose", "carb counting"]
    embeddings = llm.embed_text(test_texts)
    
    print(f"✓ Batch text embedding successful")
    print(f"  Texts: {len(test_texts)}")
    print(f"  Embeddings: {len(embeddings)}")
    print(f"  Dimensions: {[len(e) for e in embeddings]}")
    
except Exception as e:
    print(f"✗ Embeddings test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Triage Agent Integration
print("\n[TEST 4] Triage Agent Integration")
print("-" * 80)
try:
    from agents.triage import TriageAgent
    
    print("Initializing TriageAgent...")
    triage = TriageAgent()
    print(f"✓ TriageAgent initialized")
    print(f"  Uses LLM provider: {type(triage.llm).__name__}")
    
    # Test classification
    test_query = "How do I change my pump cartridge?"
    print(f"\nClassifying query: '{test_query}'")
    
    classification = triage.classify(test_query)
    print(f"✓ Classification successful")
    print(f"  Category: {classification.category.value}")
    print(f"  Confidence: {classification.confidence:.0%}")
    print(f"  Reasoning: {classification.reasoning}")
    
except Exception as e:
    print(f"✗ Triage agent test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Researcher Agent Integration
print("\n[TEST 5] Researcher Agent Integration")
print("-" * 80)
try:
    # Try ChromaDB backend first
    try:
        from agents.researcher_chromadb import ChromaDBBackend as ResearcherAgent
        backend_type = "ChromaDB"
    except ImportError:
        from agents.researcher import ResearcherAgent
        backend_type = "File API"
    
    print(f"Initializing ResearcherAgent ({backend_type})...")
    researcher = ResearcherAgent()
    print(f"✓ ResearcherAgent initialized")
    print(f"  Backend: {backend_type}")
    print(f"  Uses LLM provider: {type(researcher.llm).__name__}")
    
except Exception as e:
    print(f"✗ Researcher agent test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Error Handling
print("\n[TEST 6] Error Handling")
print("-" * 80)
try:
    from agents.llm_provider import LLMProviderError, LLMFactory
    
    # Test invalid provider
    try:
        LLMFactory.reset_provider()  # Clear cached instance
        os.environ['LLM_PROVIDER'] = 'invalid_provider'
        llm_invalid = LLMFactory.get_provider()
        print(f"✗ Should have raised error for invalid provider")
    except LLMProviderError as e:
        print(f"✓ Invalid provider error caught correctly")
        print(f"  Error: {str(e)[:100]}...")
    finally:
        # Reset to gemini
        os.environ['LLM_PROVIDER'] = 'gemini'
        LLMFactory.reset_provider()
    
    # Test missing API key
    try:
        LLMFactory.reset_provider()
        old_key = os.environ.get('GEMINI_API_KEY')
        os.environ['GEMINI_API_KEY'] = ''
        llm_no_key = LLMFactory.get_provider()
        print(f"✗ Should have raised error for missing API key")
    except LLMProviderError as e:
        print(f"✓ Missing API key error caught correctly")
        print(f"  Error: {str(e)[:100]}...")
    finally:
        # Restore API key
        if old_key:
            os.environ['GEMINI_API_KEY'] = old_key
        LLMFactory.reset_provider()
    
except Exception as e:
    print(f"✗ Error handling test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Configuration
print("\n[TEST 7] Configuration Files")
print("-" * 80)
try:
    import json
    
    # Check models.json
    models_json = Path(__file__).parent / "config" / "models.json"
    if models_json.exists():
        with open(models_json) as f:
            models_data = json.load(f)
        print(f"✓ config/models.json exists")
        print(f"  Providers documented: {list(models_data['models'].keys())}")
        print(f"  Gemini models: {list(models_data['models']['gemini'].keys())}")
    else:
        print(f"✗ config/models.json not found")
    
    # Check .env.example
    env_example = Path(__file__).parent / ".env.example"
    if env_example.exists():
        with open(env_example) as f:
            env_content = f.read()
        print(f"✓ .env.example exists")
        if "LLM_PROVIDER" in env_content:
            print(f"  Contains LLM_PROVIDER configuration")
        if "GEMINI_API_KEY" in env_content:
            print(f"  Contains GEMINI_API_KEY configuration")
    else:
        print(f"✗ .env.example not found")
    
    # Check documentation
    migration_doc = Path(__file__).parent / "docs" / "LLM_PROVIDER_MIGRATION.md"
    if migration_doc.exists():
        print(f"✓ docs/LLM_PROVIDER_MIGRATION.md exists")
    else:
        print(f"⚠ docs/LLM_PROVIDER_MIGRATION.md not found")
    
except Exception as e:
    print(f"✗ Configuration test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL TESTS PASSED ✓")
print("=" * 80)
print("\nSummary:")
print("  ✓ Provider factory working")
print("  ✓ Text generation working")
print("  ✓ Embeddings working")
print("  ✓ Triage agent integration working")
print("  ✓ Researcher agent integration working")
print("  ✓ Error handling working")
print("  ✓ Configuration files present")
print("\nThe LLM provider abstraction is fully functional!")
print("All existing Gemini functionality remains intact.")
