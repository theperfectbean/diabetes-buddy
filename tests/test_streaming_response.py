#!/usr/bin/env python3
"""
Test streaming endpoint to see what data format is actually being sent
"""
import requests
import sys

url = "http://localhost:8000/api/query/stream"
params = {"query": "How should I prepare for exercise?"}

print("📡 Testing streaming endpoint...")
print(f"URL: {url}")
print(f"Query: {params['query']}\n")

try:
    response = requests.get(url, params=params, stream=True, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}\n")
    
    print("📥 Streaming chunks:")
    print("-" * 80)
    
    chunk_count = 0
    full_text = ""
    
    for line in response.iter_lines(decode_unicode=True):
        if line:
            chunk_count += 1
            print(f"Chunk {chunk_count}: {line[:100]}{'...' if len(line) > 100 else ''}")
            
            # Parse SSE format
            if line.startswith("data: "):
                data = line[6:]  # Remove "data: " prefix
                full_text += data
    
    print("-" * 80)
    print(f"\n✅ Received {chunk_count} chunks")
    print(f"📝 Full accumulated text (first 500 chars):\n")
    print(full_text[:500])
    print("\n...")
    
    # Check for paragraph breaks
    double_newline_count = full_text.count('\n\n')
    print(f"\n🔍 Analysis:")
    print(f"   - Total length: {len(full_text)} characters")
    print(f"   - Double newlines (\\n\\n): {double_newline_count}")
    print(f"   - Single newlines (\\n): {full_text.count(chr(10)) - double_newline_count * 2}")
    
    if double_newline_count > 0:
        print(f"   ✅ Backend IS sending paragraph breaks (\\n\\n)")
    else:
        print(f"   ⚠️  Backend NOT sending paragraph breaks")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
