#!/usr/bin/env python3
"""
Direct test of the flights API endpoint
"""

import requests
import sys
import json
import time

def test_flights_api():
    url = "http://localhost:5050/api/flights?limit=1"
    
    print("=" * 60)
    print("Testing Flights API")
    print("=" * 60)
    print(f"URL: {url}")
    print()
    
    # Test 1: Basic connection
    print("1. Testing server connection...")
    try:
        response = requests.get("http://localhost:5050/", timeout=3)
        print(f"   ✓ Server is running (status: {response.status_code})")
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Server not responding: {e}")
        print("   → Make sure server is running: python3 flight_tracker_server.py")
        return False
    
    # Test 2: API endpoint
    print("\n2. Testing /api/flights endpoint...")
    print("   Sending request...")
    
    start_time = time.time()
    try:
        response = requests.get(url, timeout=10)
        elapsed = time.time() - start_time
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response Time: {elapsed:.2f} seconds")
        print(f"   Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        print(f"   Content Length: {len(response.content)} bytes")
        
        if elapsed > 5:
            print(f"   ⚠️  WARNING: Response took {elapsed:.2f} seconds (slow!)")
        
        if response.status_code == 404:
            print("\n   ✗ 404 Not Found - Endpoint doesn't exist!")
            print("   → Server needs to be restarted to load new code")
            print(f"   Response body: {response.text[:200]}")
            return False
        
        if response.status_code != 200:
            print(f"\n   ✗ Error: HTTP {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"\n   ✓ Response is valid JSON")
            print(f"   Keys in response: {list(data.keys())}")
            
            if 'flights' in data:
                flights = data['flights']
                print(f"   Number of flights: {data.get('count', len(flights))}")
                print(f"   Flights is list: {isinstance(flights, list)}")
                
                if flights and len(flights) > 0:
                    flight = flights[0]
                    print(f"\n   First flight:")
                    print(f"     ID: {flight.get('id')}")
                    print(f"     Callsign: {flight.get('callsign')}")
                    print(f"     ICAO: {flight.get('aircraft_icao')}")
                    print(f"     Origin: {flight.get('origin')}")
                    print(f"     Destination: {flight.get('destination')}")
                    print(f"     Status: {flight.get('status')}")
                    print(f"     Start Time: {flight.get('start_time')}")
                    return True
                else:
                    print("\n   ⚠️  No flights in response (empty list)")
                    print("   → Database might be empty or no flights match criteria")
                    return True  # This is OK, just no data
            else:
                print(f"\n   ✗ Response missing 'flights' key")
                print(f"   Response: {json.dumps(data, indent=2)[:500]}")
                return False
                
        except json.JSONDecodeError as e:
            print(f"\n   ✗ Response is not valid JSON")
            print(f"   Error: {e}")
            print(f"   Response (first 500 chars): {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"\n   ✗ Request timed out after 10 seconds")
        print("   → API endpoint is hanging or very slow")
        print("   → Check server terminal for errors")
        return False
    except requests.exceptions.RequestException as e:
        print(f"\n   ✗ Request failed: {e}")
        return False

if __name__ == '__main__':
    print()
    success = test_flights_api()
    print()
    print("=" * 60)
    if success:
        print("✅ Test completed successfully!")
        print("   API is working - check browser console if page still doesn't load")
    else:
        print("❌ Test failed")
        print("   Fix the issues above and try again")
    print("=" * 60)
    print()
    sys.exit(0 if success else 1)

