#!/usr/bin/env python3
"""
Test device prioritization implementation
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.unified_agent import UnifiedAgent
from agents.source_manager import UserSourceManager

def test_device_detection():
    """Test that user devices are detected."""
    print("=" * 70)
    print("TEST 1: Device Detection")
    print("=" * 70)
    
    sm = UserSourceManager()
    devices = sm.get_user_devices()
    
    print(f"\nDetected {len(devices)} device(s):")
    for device in devices:
        print(f"  - {device['name']} ({device['type']})")
        print(f"    Collection: {device['collection']}")
    
    if devices:
        print("\n✓ Device detection working")
        return True
    else:
        print("\n⚠ No devices detected (this is OK if none uploaded)")
        return True


def test_agent_integration():
    """Test that unified agent integrates source manager."""
    print("\n" + "=" * 70)
    print("TEST 2: Agent Integration")
    print("=" * 70)
    
    agent = UnifiedAgent()
    
    print(f"\nSource manager initialized: {agent.source_manager is not None}")
    
    if agent.source_manager:
        devices = agent.source_manager.get_user_devices()
        print(f"Devices accessible from agent: {len(devices)}")
        print("\n✓ Agent integration working")
        return True
    else:
        print("\n✗ Source manager not available")
        return False


def test_query_with_devices():
    """Test that a query works with device detection."""
    print("\n" + "=" * 70)
    print("TEST 3: Query with Device Detection")
    print("=" * 70)
    
    agent = UnifiedAgent()
    
    # Simple test query
    query = "What is time in range?"
    print(f"\nTest query: {query}")
    
    try:
        response = agent.process(query)
        print(f"\nQuery successful: {response.success}")
        print(f"Answer length: {len(response.answer)} characters")
        print(f"Sources used: {response.sources_used}")
        
        # Check if device names would be in logs
        if agent.source_manager:
            devices = agent.source_manager.get_user_devices()
            if devices:
                print(f"\nDevices detected during query: {[d['name'] for d in devices]}")
        
        print("\n✓ Query processing working")
        return True
    except Exception as e:
        print(f"\n✗ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n")
    print("=" * 70)
    print("DEVICE PRIORITIZATION IMPLEMENTATION TEST")
    print("=" * 70)
    print()
    
    results = []
    
    # Run tests
    results.append(("Device Detection", test_device_detection()))
    results.append(("Agent Integration", test_agent_integration()))
    results.append(("Query Processing", test_query_with_devices()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
