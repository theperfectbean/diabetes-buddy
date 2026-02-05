#!/usr/bin/env python3
"""
Minimal server test for Diabetes Buddy streaming implementation.

Tests that the FastAPI app can be imported and endpoints are registered
without requiring API keys or full dependencies.
"""

import sys
import os
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_fastapi_app_import():
    """Test that the FastAPI app can be imported."""
    print("Testing FastAPI app import...")

    try:
        # Set dummy environment variables to avoid import errors
        os.environ['GEMINI_API_KEY'] = 'dummy_key_for_testing'
        os.environ['GEMINI_MODEL'] = 'gemini/gemini-2.5-flash'

        # Try to import the app
        from web.app import app

        print("✅ FastAPI app imported successfully")

        # Check that the app has the expected routes
        routes = [route.path for route in app.routes]
        print(f"Found {len(routes)} routes: {routes[:5]}...")  # Show first 5

        # Check for our streaming endpoint
        streaming_route = "/api/query/stream"
        if any(streaming_route in route for route in routes):
            print(f"✅ Streaming endpoint '{streaming_route}' found")
        else:
            print(f"❌ Streaming endpoint '{streaming_route}' not found")
            return False

        # Check for regular query endpoints
        query_routes = ["/api/query", "/api/query/unified"]
        for route in query_routes:
            if any(route in r for r in routes):
                print(f"✅ Query endpoint '{route}' found")
            else:
                print(f"❌ Query endpoint '{route}' not found")
                return False

        return True

    except ImportError as e:
        print(f"❌ Could not import FastAPI app: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing FastAPI app: {e}")
        return False

def test_static_files():
    """Test that static files exist."""
    print("\nTesting static files...")

    static_dir = Path("/home/gary/diabetes-buddy/web/static")
    required_files = ["app.js", "styles.css"]

    for filename in required_files:
        filepath = static_dir / filename
        if filepath.exists():
            print(f"✅ Static file '{filename}' exists")
        else:
            print(f"❌ Static file '{filename}' missing")
            return False

    return True

def test_html_template():
    """Test that the HTML template exists and has expected elements."""
    print("\nTesting HTML template...")

    html_file = Path("/home/gary/diabetes-buddy/web/index.html")
    if not html_file.exists():
        print("❌ index.html not found")
        return False

    try:
        with open(html_file, 'r') as f:
            content = f.read()

        # Check for required elements
        required_elements = [
            'chatMessages',
            'queryInput',
            'sendBtn',
            'app.js',
            'styles.css'
        ]

        for element in required_elements:
            if element in content:
                print(f"✅ HTML contains '{element}'")
            else:
                print(f"❌ HTML missing '{element}'")
                return False

        print("✅ HTML template structure correct")
        return True

    except Exception as e:
        print(f"❌ Error reading HTML file: {e}")
        return False

def main():
    """Run all server tests."""
    print("=" * 60)
    print("Diabetes Buddy Server Structure Test")
    print("=" * 60)

    tests_passed = 0
    total_tests = 3

    # Test 1: FastAPI app import
    if test_fastapi_app_import():
        tests_passed += 1

    # Test 2: Static files
    if test_static_files():
        tests_passed += 1

    # Test 3: HTML template
    if test_html_template():
        tests_passed += 1

    print("\n" + "=" * 60)
    print(f"Server Test Results: {tests_passed}/{total_tests} tests passed")
    print("=" * 60)

    if tests_passed == total_tests:
        print("🎉 Server structure is correct! Ready for deployment.")
        print("\nTo run the server:")
        print("1. Copy .env.example to .env and add your GEMINI_API_KEY")
        print("2. Run: docker compose up -d")
        print("3. Open: http://localhost:8000")
        return 0
    else:
        print("⚠️  Server structure has issues. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())