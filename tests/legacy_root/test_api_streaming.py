#!/usr/bin/env python3
"""
Test streaming through the FastAPI endpoint
Verifies end-to-end: LLM -> UnifiedAgent -> FastAPI SSE -> Browser
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_api_streaming():
    """Test streaming through FastAPI endpoint"""
    import aiohttp
    
    print("=" * 70)
    print("Testing Streaming API Endpoint: GET /api/query/stream")
    print("=" * 70)
    
    url = "http://localhost:8000/api/query/stream?query=diabetes+basics"
    
    print(f"\nEndpoint: {url}")
    print("-" * 70)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"✗ HTTP {response.status}")
                    return False
                
                print(f"✓ HTTP {response.status}")
                print(f"✓ Content-Type: {response.headers.get('Content-Type')}")
                
                # Verify SSE headers
                content_type = response.headers.get('Content-Type', '')
                if 'text/event-stream' not in content_type:
                    print(f"✗ Wrong Content-Type (expected: text/event-stream, got: {content_type})")
                    return False
                
                if 'no-cache' not in response.headers.get('Cache-Control', ''):
                    print("✗ Missing Cache-Control: no-cache")
                    return False
                
                print("✓ Correct SSE headers")
                
                # Read streaming response
                chunk_count = 0
                data_count = 0
                event_count = 0
                total_chars = 0
                
                print("\nReading stream...")
                print("-" * 70)
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    
                    if line.startswith('data: '):
                        data_count += 1
                        chunk_data = line[6:]  # Remove 'data: ' prefix
                        total_chars += len(chunk_data)
                        
                        if data_count == 1:
                            print(f"First chunk: {chunk_data[:50]}...")
                    
                    elif line.startswith('event: '):
                        event = line[7:]  # Remove 'event: ' prefix
                        event_count += 1
                        if event == 'end':
                            print(f"\n✓ Received 'event: end' signal")
                    
                    elif line == '':
                        chunk_count += 1
                    
                    # Limit for testing
                    if data_count >= 100:
                        break
                
                print(f"\n✓ Received {chunk_count} complete messages")
                print(f"✓ Received {data_count} data chunks")
                print(f"✓ Total characters streamed: {total_chars}")
                print(f"✓ Event signals received: {event_count}")
                
                if chunk_count > 0 and data_count > 0:
                    print("\n✅ API Streaming Test PASSED!")
                    return True
                else:
                    print("\n✗ Stream was empty")
                    return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n📡 Diabetes Buddy API Streaming Test\n")
    
    try:
        result = asyncio.run(test_api_streaming())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
