#!/usr/bin/env python3
"""
Test the Glooko upload functionality
"""

import io
import json
import zipfile
import requests
from pathlib import Path

# Create a test ZIP file with sample CSV data
def create_test_zip():
    """Create a minimal test ZIP with sample Glooko data"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Sample glucose data
        glucose_csv = """Date,Time,Glucose Value (mg/dL),Device
2024-01-20,08:00,120,FreeStyle Libre
2024-01-20,08:15,125,FreeStyle Libre
2024-01-20,08:30,130,FreeStyle Libre
"""
        zip_file.writestr('glucose.csv', glucose_csv)
        
        # Sample insulin data
        insulin_csv = """Date,Time,Insulin Type,Units
2024-01-20,08:00,Bolus,2.5
2024-01-20,12:00,Bolus,4.0
"""
        zip_file.writestr('insulin.csv', insulin_csv)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def test_upload():
    """Test uploading a Glooko file"""
    print("Creating test ZIP file...")
    test_zip = create_test_zip()
    print(f"Test ZIP created, size: {len(test_zip)} bytes")
    
    # Test the upload endpoint
    print("\nTesting upload to http://localhost:8000/api/upload-glooko")
    
    files = {'file': ('test_glooko.zip', test_zip, 'application/zip')}
    
    try:
        response = requests.post(
            'http://localhost:8000/api/upload-glooko',
            files=files,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✓ Upload successful!")
        else:
            print("\n✗ Upload failed!")
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_upload()
