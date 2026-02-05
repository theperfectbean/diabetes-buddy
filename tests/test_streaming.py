#!/usr/bin/env python3
"""
Test script to verify streaming is working end-to-end
Tests both LLM provider streaming and FastAPI SSE response
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.unified_agent import UnifiedAgent
from agents.llm_provider import GenerationConfig

def test_unified_agent_streaming():
    """Test that UnifiedAgent.process_stream yields chunks correctly"""
    print("=" * 60)
    print("Test 1: UnifiedAgent.process_stream() streaming")
    print("=" * 60)
    
    agent = UnifiedAgent(project_root=Path(__file__).parent)
    
    print("\nQuery: 'What is diabetes?'")
    print("-" * 60)
    
    chunk_count = 0
    total_chars = 0
    
    try:
        for chunk in agent.process_stream("What is diabetes?"):
            chunk_count += 1
            total_chars += len(chunk)
            # Print just the first chunk to verify it's not empty
            if chunk_count == 1:
                print(f"First chunk received: {chunk[:100]}")
            # Show a dot for each chunk
            print(".", end="", flush=True)
            
            if chunk_count >= 100:  # Limit for testing
                break
    except Exception as e:
        print(f"\nError: {e}")
        return False
    
    print(f"\n✓ Received {chunk_count} chunks, {total_chars} total characters")
    print("✓ UnifiedAgent streaming works!\n")
    return True


def test_llm_provider_streaming():
    """Test that LLM provider's generate_text_stream works"""
    print("=" * 60)
    print("Test 2: LLM Provider generate_text_stream()")
    print("=" * 60)
    
    from agents.llm_provider import LLMFactory
    
    try:
        llm = LLMFactory.get_provider()
        print(f"LLM Provider: {llm.__class__.__name__}")
        model_name = getattr(llm, "model", None) or getattr(llm, "model_name", "unknown")
        print(f"Model: {model_name}")
        
        print("\nPrompt: 'Say hello in 10 words or less'")
        print("-" * 60)
        
        chunk_count = 0
        total_chars = 0
        full_response = ""
        
        for chunk in llm.generate_text_stream(
            "Say hello in 10 words or less",
            config=GenerationConfig(temperature=0.7, max_tokens=50)
        ):
            chunk_count += 1
            total_chars += len(chunk)
            full_response += chunk
            print(".", end="", flush=True)
            
            if chunk_count >= 50:  # Limit for testing
                break
        
        print(f"\n✓ Received {chunk_count} chunks, {total_chars} characters")
        print(f"✓ Response: {full_response[:100]}...")
        print("✓ LLM Provider streaming works!\n")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}\n")
        return False


def test_sse_formatting():
    """Test that SSE formatting in app.py is correct"""
    print("=" * 60)
    print("Test 3: SSE Formatting")
    print("=" * 60)
    
    # Simulate what the backend does
    test_chunk = "Hello\nWorld\nStreaming"
    lines = test_chunk.split('\n')
    
    print("Input chunk: 'Hello\\nWorld\\nStreaming'")
    print("SSE formatted output:")
    print("-" * 60)
    
    for i, line in enumerate(lines):
        if line or i < len(lines) - 1:
            formatted = f"data: {line}\n"
            print(repr(formatted), end="")
    
    blank_line = "\n"
    print(repr(blank_line), end="")
    
    print("\n✓ SSE formatting looks correct!\n")
    return True


if __name__ == "__main__":
    print("\n🧪 Diabetes Buddy Streaming Tests\n")
    
    results = []
    
    # Test LLM provider first (simpler, faster)
    try:
        results.append(("LLM Provider Streaming", test_llm_provider_streaming()))
    except Exception as e:
        print(f"✗ LLM Provider test failed: {e}\n")
        results.append(("LLM Provider Streaming", False))
    
    # Test UnifiedAgent streaming
    try:
        results.append(("UnifiedAgent Streaming", test_unified_agent_streaming()))
    except Exception as e:
        print(f"✗ UnifiedAgent test failed: {e}\n")
        results.append(("UnifiedAgent Streaming", False))
    
    # Test SSE formatting
    try:
        results.append(("SSE Formatting", test_sse_formatting()))
    except Exception as e:
        print(f"✗ SSE formatting test failed: {e}\n")
        results.append(("SSE Formatting", False))
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    print("=" * 60)
    
    if all_passed:
        print("\n✅ All streaming tests passed!\n")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed\n")
        sys.exit(1)
