#!/usr/bin/env python3
"""
dump1090 Flight Feed
Continuously fetches and displays aircraft detected by dump1090
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
from flight_info import get_flight_route

def load_config():
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: config.json not found")
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

def display_aircraft(data, flight_memory, limit=20, clear_screen=False):
    """Display aircraft information"""
    if not data:
        return []
    
    # Clear screen if requested (do this BEFORE checking for aircraft)
    if clear_screen:
        os.system('clear' if os.name != 'nt' else 'cls')
    
    aircraft = data.get('aircraft', [])
    
    # Filter out aircraft without callsigns
    aircraft_with_callsigns = [ac for ac in aircraft if ac.get('flight', '').strip()]
    
    # Filter out stale data (seen > 60 seconds ago)
    recent_aircraft = [ac for ac in aircraft_with_callsigns if ac.get('seen', 999) <= 60]
    
    # Print header (always show this, even if no aircraft)
    print(f"{'='*80}")
    print(f"Flight Feed - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Active flights: {len(recent_aircraft)} (from {len(aircraft_with_callsigns)} with callsigns, {len(aircraft)} total)")
    print(f"{'='*80}")
    
    # If no recent aircraft, show message and return
    if not recent_aircraft:
        print("\nNo flights detected")
        print(f"\n{'='*80}")
        print("Press Ctrl+C to exit")
        return []
    
    # Display recent aircraft (limited)
    for i, ac in enumerate(recent_aircraft[:limit], 1):
        icao = ac.get('hex', 'Unknown')
        callsign = ac.get('flight', '').strip()
        altitude = ac.get('alt_baro') or ac.get('altitude')
        speed = ac.get('gs')
        track = ac.get('track')
        lat = ac.get('lat')
        lon = ac.get('lon')
        
        # Check if in memory
        status = 'saved' if icao in flight_memory else 'new'
        
        print(f"\n{i}. ICAO: {icao}")
        print(f"   Callsign: {callsign}")
        print(f"   Status: {status}")
        
        # Show seen cycles if in memory
        if icao in flight_memory:
            seen_cycles = flight_memory[icao].get('seen_cycles', 0)
            print(f"   Seen cycles: {seen_cycles}")
        
        # Show route info if available in memory
        if icao in flight_memory:
            origin = flight_memory[icao].get('origin')
            destination = flight_memory[icao].get('destination')
            if origin:
                if destination:
                    print(f"   Route: {origin} → {destination}")
                else:
                    print(f"   Origin: {origin} (destination not yet determined)")
            else:
                # Debug: Show if we've tried to lookup
                if flight_memory[icao].get('lookup_attempted'):
                    if flight_memory[icao].get('lookup_error'):
                        error = flight_memory[icao]['lookup_error']
                        if 'rate_limited' in error or '429' in error:
                            print(f"   Route: Rate limited (feeder status may take 24-48h to activate)")
                        else:
                            print(f"   Route: Not found (API lookup attempted)")
                else:
                    print(f"   Route: Pending lookup...")
        
        if altitude:
            print(f"   Altitude: {altitude:,} ft")
        if speed:
            print(f"   Speed: {speed:.1f} kts")
        if track is not None:
            print(f"   Track: {track:.1f}°")
        if lat and lon:
            print(f"   Position: {lat:.4f}, {lon:.4f}")
    
    if len(recent_aircraft) > limit:
        print(f"\n... and {len(recent_aircraft) - limit} more aircraft")
    
    print(f"\n{'='*80}")
    print("Press Ctrl+C to exit")
    
    return recent_aircraft

def main():
    """Main loop"""
    config = load_config()
    dump1090_url = config['dump1090_url']
    
    print("Starting dump1090 flight feed...")
    print(f"Fetching from: {dump1090_url}")
    print("Clear screen enabled - updates will refresh in place\n")
    time.sleep(2)  # Brief pause before first update
    
    # Initialize flight memory: {icao: {'callsign': '...', 'missed_cycles': 0}}
    flight_memory = {}
    cycle_counter = 0
    
    try:
        first_run = True
        while True:
            data = get_aircraft(dump1090_url)
            if data:
                recent_aircraft = display_aircraft(data, flight_memory, clear_screen=(not first_run))
                first_run = False
                
                # Update memory with current flights
                current_icaos = set()
                if recent_aircraft:
                    for ac in recent_aircraft:
                        icao = ac.get('hex', 'Unknown')
                        callsign = ac.get('flight', '').strip()
                        current_icaos.add(icao)
                        
                        # Add new flights or update existing ones
                        if icao not in flight_memory:
                            # New flight - lookup route info
                            flight_memory[icao] = {
                                'callsign': callsign,
                                'missed_cycles': 0,
                                'seen_cycles': 0,
                                'origin': None,
                                'destination': None,
                                'lookup_attempted': False
                            }
                            
                            # Lookup route information (only for new flights, requires callsign)
                            if callsign and icao != 'Unknown':
                                try:
                                    flight_memory[icao]['lookup_attempted'] = True
                                    # Pass lat/lon if available from current aircraft data
                                    lat = ac.get('lat')
                                    lon = ac.get('lon')
                                    route_info = get_flight_route(icao, callsign, lat, lon)
                                    if route_info:
                                        if route_info.get('error'):
                                            # Store error (like rate limiting)
                                            flight_memory[icao]['lookup_error'] = route_info.get('error')
                                        else:
                                            flight_memory[icao]['origin'] = route_info.get('origin')
                                            flight_memory[icao]['destination'] = route_info.get('destination')
                                            flight_memory[icao]['source'] = route_info.get('source', 'unknown')
                                except Exception as e:
                                    # Store error for debugging
                                    flight_memory[icao]['lookup_error'] = str(e)
                        else:
                            flight_memory[icao]['missed_cycles'] = 0  # Reset counter
                            flight_memory[icao]['seen_cycles'] = flight_memory[icao].get('seen_cycles', 0) + 1
                            
                            # Retry route lookup on 5th cycle if no route info yet (requires callsign)
                            if flight_memory[icao]['seen_cycles'] == 5:
                                if not flight_memory[icao].get('origin') and callsign and icao != 'Unknown':
                                    try:
                                        flight_memory[icao]['lookup_attempted'] = True
                                        # Pass lat/lon if available
                                        lat = ac.get('lat')
                                        lon = ac.get('lon')
                                        route_info = get_flight_route(icao, callsign, lat, lon)
                                        if route_info:
                                            if route_info.get('error'):
                                                flight_memory[icao]['lookup_error'] = route_info.get('error')
                                            else:
                                                flight_memory[icao]['origin'] = route_info.get('origin')
                                                flight_memory[icao]['destination'] = route_info.get('destination')
                                                flight_memory[icao]['source'] = route_info.get('source', 'unknown')
                                    except Exception as e:
                                        flight_memory[icao]['lookup_error'] = str(e)
                    
                    # Increment missed cycles for flights not seen
                    for icao in flight_memory:
                        if icao not in current_icaos:
                            flight_memory[icao]['missed_cycles'] += 1
                    
                    # Remove flights that have been missing for 10 cycles
                    flights_to_remove = [icao for icao, info in flight_memory.items() 
                                       if info['missed_cycles'] >= 10]
                    for icao in flights_to_remove:
                        del flight_memory[icao]
                    
                    cycle_counter += 1
            time.sleep(5)  # Update every 5 seconds
    except KeyboardInterrupt:
        print("\n\nStopping feed...")
        sys.exit(0)

if __name__ == '__main__':
    main()
