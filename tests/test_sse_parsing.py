#!/usr/bin/env python3
"""
Simulate browser EventSource parsing of SSE to verify paragraph breaks
"""
import requests

url = "http://localhost:8000/api/query/stream"
params = {"query": "How should I prepare for exercise?"}

print("📡 Simulating Browser EventSource SSE Parsing...\n")

try:
    response = requests.get(url, params=params, stream=True, timeout=30)
    
    current_event = {"data": []}
    messages = []
    
    for line in response.iter_lines(decode_unicode=True):
        if not line:  # Empty line = end of message
            if current_event["data"]:
                # Join all data lines with \n (per SSE spec)
                full_data = '\n'.join(current_event["data"])
                messages.append(full_data)
                current_event = {"data": []}
            continue
            
        if line.startswith("data: "):
            # Extract data after "data: " prefix
            data_content = line[6:]  # Remove "data: "
            current_event["data"].append(data_content)
        elif line.startswith("event: "):
            break  # Stop at end event
    
    # Combine all messages (this is what fullResponse would be in JS)
    full_text = ''.join(messages)
    
    print(f"✅ Parsed {len(messages)} SSE messages\n")
    print(f"📝 Full accumulated text (first 600 chars):")
    print(full_text[:600])
    print("\n...\n")
    
    # Analysis
    double_newlines = full_text.count('\n\n')
    print(f"🔍 Analysis:")
    print(f"   - Total length: {len(full_text)} characters")
    print(f"   - Double newlines (\\n\\n): {double_newlines}")
    
    if double_newlines >= 2:
        print(f"   ✅ SUCCESS! Backend IS sending paragraph breaks via SSE")
        print(f"   ✅ JavaScript .replace(/\\n\\n/g, '<br><br>') will work!")
    else:
        print(f"   ❌ PROBLEM: Still no paragraph breaks in parsed SSE")
        
        # Debug: show first few messages
        print(f"\n🔬 First 5 messages (EventSource events):")
        for i, msg in enumerate(messages[:5]):
            print(f"   Message {i+1}: {repr(msg[:80])}")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
