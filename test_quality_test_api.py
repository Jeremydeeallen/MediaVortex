#!/usr/bin/env python3
"""
Test the simple QualityTest API endpoints
"""

import requests
import json
import time

def TestQualityTestAPI():
    """Test the QualityTest API endpoints"""
    base_url = "http://localhost:5000"
    
    print("Testing QualityTest API endpoints...")
    
    # Test 1: Get QualityTest Queue
    print("\n1. Testing GET /api/QualityTest/Queue")
    try:
        response = requests.get(f"{base_url}/api/QualityTest/Queue")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            print("✅ GET /api/QualityTest/Queue - SUCCESS")
        else:
            print(f"❌ GET /api/QualityTest/Queue - FAILED: {response.text}")
    except Exception as e:
        print(f"❌ GET /api/QualityTest/Queue - ERROR: {e}")
    
    # Test 2: Get QualityTest Status (for a specific job)
    print("\n2. Testing GET /api/QualityTest/Status/1")
    try:
        response = requests.get(f"{base_url}/api/QualityTest/Status/1")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            print("✅ GET /api/QualityTest/Status/1 - SUCCESS")
        else:
            print(f"❌ GET /api/QualityTest/Status/1 - FAILED: {response.text}")
    except Exception as e:
        print(f"❌ GET /api/QualityTest/Status/1 - ERROR: {e}")
    
    # Test 3: Start QualityTest (for a specific job)
    print("\n3. Testing POST /api/QualityTest/Start")
    try:
        payload = {"JobId": 1}
        response = requests.post(
            f"{base_url}/api/QualityTest/Start",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            print("✅ POST /api/QualityTest/Start - SUCCESS")
        else:
            print(f"❌ POST /api/QualityTest/Start - FAILED: {response.text}")
    except Exception as e:
        print(f"❌ POST /api/QualityTest/Start - ERROR: {e}")
    
    print("\nQualityTest API testing completed!")

if __name__ == "__main__":
    TestQualityTestAPI()
