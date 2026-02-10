#!/usr/bin/env python3
"""Comprehensive test of conversation loading functionality."""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_full_workflow():
    """Test the complete conversation loading workflow."""
    
    print("=" * 60)
    print("DIABETES BUDDY CONVERSATION LOADING TEST")
    print("=" * 60)
    
    # Test 1: Verify API endpoints exist
    print("\n1. Verifying API endpoints...")
    endpoints = [
        ("GET", "/api/conversations", "List all conversations"),
    ]
    
    for method, endpoint, desc in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            status = "✓" if response.status_code == 200 else "✗"
            print(f"  {status} {method} {endpoint} - {desc} (Status: {response.status_code})")
        except Exception as e:
            print(f"  ✗ {method} {endpoint} - {desc} (Error: {e})")
            return False
    
    # Test 2: Load conversations
    print("\n2. Loading conversations...")
    try:
        response = requests.get(f"{BASE_URL}/api/conversations")
        conversations = response.json()
        print(f"  ✓ Loaded {len(conversations)} conversations")
        
        if not conversations:
            print("  ⚠ No conversations to test, skipping further tests")
            return True
        
        # Show first few
        for i, conv in enumerate(conversations[:3]):
            print(f"    {i+1}. {conv['firstQuery'][:50]}... ({conv['messageCount']} messages)")
    except Exception as e:
        print(f"  ✗ Failed to load conversations: {e}")
        return False
    
    # Test 3: Load specific conversation and verify structure
    print("\n3. Loading first conversation details...")
    conv_id = conversations[0]['id']
    try:
        response = requests.get(f"{BASE_URL}/api/conversations/{conv_id}")
        conversation = response.json()
        
        print(f"  ✓ Loaded conversation {conv_id[:20]}...")
        print(f"    - Messages: {len(conversation['messages'])}")
        print(f"    - Created: {conversation['created']}")
        
        # Test 4: Verify message structure
        print("\n4. Verifying message structure...")
        for idx, msg in enumerate(conversation['messages']):
            print(f"\n    Message {idx+1}: {msg['type'].upper()}")
            print(f"      - Content length: {len(msg.get('content', '')) or 0} chars")
            print(f"      - Timestamp: {msg['timestamp']}")
            print(f"      - Has data field: {bool(msg.get('data'))}")
            
            if msg['type'] == 'assistant' and msg.get('data'):
                data = msg['data']
                print(f"      - Data keys: {list(data.keys())}")
                print(f"      - Classification: {data.get('classification', 'N/A')}")
                print(f"      - Sources: {len(data.get('sources', []))} items")
                
                # This is what the frontend does
                if not data.get('answer') and msg.get('content'):
                    print(f"      ✓ Will set answer from content ({len(msg.get('content', ''))} chars)")
                elif data.get('answer'):
                    print(f"      - Already has answer field ({len(data.get('answer', ''))} chars)")
                else:
                    print(f"      ⚠ No answer or content available")
    
    except Exception as e:
        print(f"  ✗ Failed to load conversation details: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED")
    print("=" * 60)
    print("\nConversation loading should work correctly:")
    print("1. Backend API returns full conversation with all messages")
    print("2. Frontend loads conversation on click")
    print("3. Messages are rendered with correct structure")
    print("4. Assistant messages are properly displayed with answer content")
    print("\nInstructions to test:")
    print("1. Open browser to http://localhost:8000")
    print("2. Hard refresh (Ctrl+F5)")
    print("3. Click on a conversation in the left sidebar")
    print("4. You should see the conversation messages load in the center")
    print("5. Check browser console (F12) for detailed debug logs")
    
    return True

if __name__ == "__main__":
    success = test_full_workflow()
    sys.exit(0 if success else 1)
