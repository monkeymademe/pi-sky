#!/usr/bin/env python3
"""
Raw dump1090 Feed - No Filters
Continuously fetches and displays ALL aircraft detected by dump1090
No filtering by callsign, age, or any other criteria
"""

import sys
import os
import warnings

# Suppress urllib3 warning
os.environ['PYTHONWARNINGS'] = 'ignore:urllib3'
warnings.filterwarnings('ignore', message='.*urllib3.*')

import requests
import json
import time
from datetime import datetime

def load_config():
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("=" * 80)
        print("ERROR: config.json not found")
        print("=" * 80)
        print("\nTo get started:")
        print("  1. Copy config_template.json to config.json:")
        print("     cp config_template.json config.json")
        print("\n  2. Edit config.json with your settings:")
        print("     - Update dump1090_url if your dump1090 is on a different host/port")
        print("     - Set your receiver_lat and receiver_lon coordinates")
        print("     - Adjust other settings as needed")
        print("\n" + "=" * 80)
        sys.exit(1)

def get_aircraft(dump1090_url):
    """Fetch aircraft data from dump1090"""
    try:
        response = requests.get(dump1090_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching from dump1090: {e}")
        return None

def display_aircraft(data, clear_screen=False):
    """Display ALL aircraft information - NO FILTERS"""
    if not data:
        return []
    
    # Clear screen if requested (do this BEFORE checking for aircraft)
    if clear_screen:
        os.system('clear' if os.name != 'nt' else 'cls')
    
    aircraft = data.get('aircraft', [])
    
    # NO FILTERING - Show ALL aircraft from dump1090
    # No filter by callsign, no filter by age, no limit on count
    
    # Print header (always show this, even if no aircraft)
    print(f"{'='*80}")
    print(f"Raw dump1090 Feed - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total aircraft detected: {len(aircraft)}")
    print(f"{'='*80}")
    
    # If no aircraft, show message and return
    if not aircraft:
        print("\nNo aircraft detected")
        print(f"\n{'='*80}")
        print("Press Ctrl+C to exit")
        return []
    
    # Display ALL aircraft (no limit)
    for i, ac in enumerate(aircraft, 1):
        icao = ac.get('hex', 'Unknown')
        callsign = ac.get('flight', '').strip() or 'N/A'
        altitude = ac.get('alt_baro') or ac.get('altitude')
        speed = ac.get('gs')
        track = ac.get('track')
        lat = ac.get('lat')
        lon = ac.get('lon')
        seen = ac.get('seen', None)  # Time since last seen (in seconds)
        squawk = ac.get('squawk')
        category = ac.get('category')
        
        print(f"\n{i}. ICAO: {icao}")
        print(f"   Callsign: {callsign}")
        
        if seen is not None:
            print(f"   Last seen: {seen:.1f} seconds ago")
        
        if altitude:
            print(f"   Altitude: {altitude:,} ft")
        if speed:
            print(f"   Speed: {speed:.1f} kts")
        if track is not None:
            print(f"   Track: {track:.1f}°")
        if lat and lon:
            print(f"   Position: {lat:.4f}, {lon:.4f}")
        if squawk:
            print(f"   Squawk: {squawk}")
        if category:
            print(f"   Category: {category}")
    
    print(f"\n{'='*80}")
    print("Press Ctrl+C to exit")
    
    return aircraft

def main():
    """Main loop"""
    config = load_config()
    dump1090_url = config['dump1090_url']
    
    print("Starting raw dump1090 feed (NO FILTERS)...")
    print(f"Fetching from: {dump1090_url}")
    print("This will show ALL aircraft detected by dump1090")
    print("- No callsign filter")
    print("- No age filter")
    print("- No limit on count")
    print("Clear screen enabled - updates will refresh in place\n")
    time.sleep(2)  # Brief pause before first update
    
    try:
        first_run = True
        while True:
            data = get_aircraft(dump1090_url)
            if data:
                display_aircraft(data, clear_screen=(not first_run))
                first_run = False
            
            time.sleep(1)  # Update every 1 second
    except KeyboardInterrupt:
        print("\n\nStopping feed...")
        sys.exit(0)

if __name__ == '__main__':
    main()


