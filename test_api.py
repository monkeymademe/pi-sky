#!/usr/bin/env python3
"""
Quick test script to check if the flights API is working
"""

import requests
import sys
import time

def test_api():
    base_url = "http://localhost:5050"
    
    print("Testing Flights API endpoints...")
    print(f"Base URL: {base_url}")
    print()
    
    # Test 1: Check if server is running
    print("1. Testing server connection...")
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        print(f"   ✓ Server is running (status: {response.status_code})")
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Server not responding: {e}")
        print("   → Make sure the server is running: python3 flight_tracker_server.py")
        return False
    
    # Test 2: Test flights API
    print("\n2. Testing /api/flights endpoint...")
    try:
        start_time = time.time()
        response = requests.get(f"{base_url}/api/flights?limit=5", timeout=15)
        elapsed = time.time() - start_time
        print(f"   Status: {response.status_code}")
        print(f"   Response time: {elapsed:.2f} seconds")
        
        if response.status_code == 404:
            print("   ✗ Endpoint not found - server needs to be restarted!")
            print("   → Stop the server (Ctrl+C) and restart: python3 flight_tracker_server.py")
            return False
        elif response.status_code != 200:
            print(f"   ✗ Error: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"   ✓ API responded successfully")
            print(f"   Flights returned: {data.get('count', 0)}")
            if data.get('flights'):
                print(f"   First flight: {data['flights'][0].get('callsign', 'Unknown')}")
        except ValueError as e:
            print(f"   ✗ Response is not JSON: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"   ✗ Request timed out after 15 seconds")
        print("   → The API is very slow or hanging")
        return False
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Request failed: {e}")
        return False
    
    # Test 3: Test with limit=1
    print("\n3. Testing with limit=1 (should be faster)...")
    try:
        start_time = time.time()
        response = requests.get(f"{base_url}/api/flights?limit=1", timeout=10)
        elapsed = time.time() - start_time
        print(f"   Response time: {elapsed:.2f} seconds")
        if elapsed > 5:
            print(f"   ⚠️  Warning: Response is slow (>5 seconds)")
        else:
            print(f"   ✓ Response time is acceptable")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "="*60)
    print("Test complete!")
    return True

if __name__ == '__main__':
    success = test_api()
    sys.exit(0 if success else 1)

