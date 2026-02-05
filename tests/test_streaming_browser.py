#!/usr/bin/env python3
"""
Test script to verify streaming functionality end-to-end.
This simulates what the browser EventSource does.
"""

import requests
import json
import time

def test_streaming_endpoint():
    """Test the streaming endpoint by simulating EventSource behavior."""
    print("Testing streaming endpoint...")

    # Test the streaming endpoint
    url = "http://localhost:8000/api/query/stream"
    params = {"query": "test streaming"}

    try:
        # Make the request
        response = requests.get(url, params=params, stream=True)
        response.raise_for_status()

        print(f"Response status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"Cache-Control: {response.headers.get('Cache-Control', 'N/A')}")
        print()

        print("Streaming data received:")
        print("-" * 50)

        chunk_count = 0
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                print(f"Chunk {chunk_count}: {repr(line_str)}")
                chunk_count += 1

                # Stop after a few chunks for testing
                if chunk_count > 10:
                    print("... (stopping after 10 chunks)")
                    break

        print("-" * 50)
        print(f"Total chunks received: {chunk_count}")
        print("✅ Streaming endpoint is working!")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error testing streaming endpoint: {e}")
        return False

    return True

def test_regular_endpoint():
    """Test the regular query endpoint for comparison."""
    print("\nTesting regular query endpoint...")

    url = "http://localhost:8000/api/query/unified"
    data = {"query": "test regular"}

    try:
        response = requests.post(url, json=data)
        response.raise_for_status()

        result = response.json()
        print(f"Response status: {response.status_code}")
        print(f"Response: {json.dumps(result, indent=2)[:200]}...")
        print("✅ Regular endpoint is working!")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error testing regular endpoint: {e}")
        return False

    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Diabetes Buddy Streaming Test")
    print("=" * 60)

    # Test both endpoints
    streaming_ok = test_streaming_endpoint()
    regular_ok = test_regular_endpoint()

    print("\n" + "=" * 60)
    print("Test Results:")
    print(f"Streaming endpoint: {'✅ PASS' if streaming_ok else '❌ FAIL'}")
    print(f"Regular endpoint: {'✅ PASS' if regular_ok else '❌ FAIL'}")

    if streaming_ok and regular_ok:
        print("\n🎉 All tests passed! Streaming should work in the browser.")
        print("\nTo test in browser:")
        print("1. Open http://localhost:8000")
        print("2. Ask a question")
        print("3. You should see text appear word by word")
        print("4. Check browser console (F12) for debug messages")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
    print("=" * 60)