#!/usr/bin/env python3
"""Test conversation loading functionality."""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_conversation_api():
    """Test the conversation API endpoints."""
    
    # Test 1: List conversations
    print("Test 1: GET /api/conversations")
    response = requests.get(f"{BASE_URL}/api/conversations")
    print(f"Status: {response.status_code}")
    conversations = response.json()
    print(f"Found {len(conversations)} conversations\n")
    
    if not conversations:
        print("No conversations found to test")
        return
    
    # Test 2: Get specific conversation
    conv_id = conversations[0]['id']
    print(f"Test 2: GET /api/conversations/{conv_id}")
    response = requests.get(f"{BASE_URL}/api/conversations/{conv_id}")
    print(f"Status: {response.status_code}")
    conversation = response.json()
    print(f"Conversation ID: {conversation['id']}")
    print(f"Messages count: {len(conversation['messages'])}")
    print(f"Created: {conversation['created']}")
    print(f"Updated: {conversation['updated']}")
    print("\nMessages:")
    for i, msg in enumerate(conversation['messages']):
        print(f"\n  Message {i+1}:")
        print(f"    Type: {msg['type']}")
        print(f"    Content length: {len(msg.get('content', ''))}")
        print(f"    Timestamp: {msg['timestamp']}")
        if msg.get('data'):
            print(f"    Has data field: Yes")
            if 'answer' in msg['data']:
                print(f"      - answer: {len(msg['data']['answer'])} chars")
            if 'sources' in msg['data']:
                print(f"      - sources: {len(msg['data']['sources'])} items")
            if 'classification' in msg['data']:
                print(f"      - classification: {msg['data']['classification']}")
        else:
            print(f"    Has data field: No")

if __name__ == "__main__":
    test_conversation_api()
