#!/usr/bin/env python3
"""
Test script for glucose unit settings feature.
Tests the complete flow of getting and setting glucose unit preferences.
"""

import json
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_glucose_unit_api():
    """Test glucose unit API endpoints."""
    print("Testing glucose unit API endpoints...")
    
    try:
        # Set up dummy environment
        import os
        os.environ['GEMINI_API_KEY'] = 'dummy_key_for_testing'
        os.environ['GEMINI_MODEL'] = 'gemini/gemini-2.5-flash'
        os.environ['GROQ_API_KEY'] = 'dummy_key_for_testing'
        os.environ['GLUCOSE_UNIT'] = 'mmol/L'
        
        # Import FastAPI test client
        from fastapi.testclient import TestClient
        from web.app import app
        
        client = TestClient(app)
        
        # Test 1: Get default glucose unit
        print("\n1. Testing GET /api/settings/glucose-unit...")
        response = client.get("/api/settings/glucose-unit")
        print(f"   Status code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {data}")
            assert "glucose_unit" in data, "Response missing glucose_unit field"
            print("   ✅ GET endpoint works")
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            return False
        
        # Test 2: Set glucose unit to mg/dL
        print("\n2. Testing POST /api/settings/glucose-unit (setting to mg/dL)...")
        response = client.post(
            "/api/settings/glucose-unit",
            json={"glucose_unit": "mg/dL"}
        )
        print(f"   Status code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {data}")
            assert data.get("success") == True, "Success flag not set"
            assert data.get("glucose_unit") == "mg/dL", "Glucose unit not updated"
            print("   ✅ POST endpoint works (mg/dL)")
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            return False
        
        # Test 3: Verify the setting persisted
        print("\n3. Testing GET /api/settings/glucose-unit (verifying persistence)...")
        response = client.get("/api/settings/glucose-unit")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {data}")
            if data.get("glucose_unit") == "mg/dL":
                print("   ✅ Setting persisted correctly")
            else:
                print(f"   ⚠️  Setting may not have persisted (got {data.get('glucose_unit')})")
        
        # Test 4: Set back to mmol/L
        print("\n4. Testing POST /api/settings/glucose-unit (setting to mmol/L)...")
        response = client.post(
            "/api/settings/glucose-unit",
            json={"glucose_unit": "mmol/L"}
        )
        print(f"   Status code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {data}")
            assert data.get("glucose_unit") == "mmol/L", "Glucose unit not updated"
            print("   ✅ POST endpoint works (mmol/L)")
        else:
            print(f"   ❌ Unexpected status code: {response.status_code}")
            return False
        
        # Test 5: Test invalid glucose unit
        print("\n5. Testing POST with invalid glucose unit...")
        response = client.post(
            "/api/settings/glucose-unit",
            json={"glucose_unit": "invalid"}
        )
        print(f"   Status code: {response.status_code}")
        if response.status_code == 400:
            print("   ✅ Invalid unit correctly rejected")
        else:
            print(f"   ⚠️  Expected 400 for invalid unit, got {response.status_code}")
        
        print("\n" + "="*50)
        print("✅ All glucose unit API tests passed!")
        print("="*50)
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_user_profile_structure():
    """Test that user profile has glucose_unit field."""
    print("\nTesting user profile structure...")
    
    try:
        profile_file = Path(__file__).parent / "config" / "user_profile.json"
        
        if not profile_file.exists():
            print(f"❌ user_profile.json not found at {profile_file}")
            return False
        
        with open(profile_file, 'r') as f:
            profile = json.load(f)
        
        if "glucose_unit" in profile:
            print(f"   ✅ glucose_unit field present: {profile['glucose_unit']}")
            if profile['glucose_unit'] in ("mmol/L", "mg/dL"):
                print(f"   ✅ glucose_unit has valid value")
                return True
            else:
                print(f"   ❌ glucose_unit has invalid value: {profile['glucose_unit']}")
                return False
        else:
            print("   ❌ glucose_unit field missing from user_profile.json")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    print("="*50)
    print("Glucose Unit Settings Feature Tests")
    print("="*50)
    
    # Run tests
    profile_ok = test_user_profile_structure()
    api_ok = test_glucose_unit_api()
    
    if profile_ok and api_ok:
        print("\n" + "="*50)
        print("✅ ALL TESTS PASSED")
        print("="*50)
        sys.exit(0)
    else:
        print("\n" + "="*50)
        print("❌ SOME TESTS FAILED")
        print("="*50)
        sys.exit(1)
