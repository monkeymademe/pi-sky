#!/usr/bin/env python3
"""
Unified Flight Tracker Server with Map Support
Combines flight data collection, HTTP server, and WebSocket broadcasting
Serves a map-enabled web interface
"""

import sys
import os
import json
import time
import asyncio
import threading
import warnings
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import TCPServer, ThreadingMixIn
from math import radians, sin, cos, sqrt, atan2
import subprocess

# Suppress urllib3 warning
os.environ['PYTHONWARNINGS'] = 'ignore:urllib3'
warnings.filterwarnings('ignore', message='.*urllib3.*')

import requests
import subprocess

from flight_info import get_flight_route, get_aircraft_info_adsblol, get_aircraft_photos_jetapi, get_airport_coordinates, get_city_name_from_coordinates
from airline_logos import get_airline_info
from flight_db import FlightDatabase

# Try to import Inky display function
try:
    from display_inky import display_image_on_inky
    HAS_INKY_DISPLAY = True
except ImportError:
    HAS_INKY_DISPLAY = False
    print("⚠️  Warning: Inky display not available (display_inky.py not found)")

# Global state
sse_clients = set()
sse_clients_lock = threading.Lock()
flight_memory = {}
latest_flight_data = None
last_map_generation_time = None  # Track when we last generated a map image
last_map_flight_icao = None  # Track which flight we last generated a map for
last_flight_detected_time = None  # Track when we last detected any flight
map_generation_lock = threading.Lock()  # Lock to prevent concurrent map generation
map_generation_in_progress = False  # Flag to track if map generation is currently running

# API call tracking
api_call_tracker = {}  # Track API calls per ICAO: {icao: {'route_calls': count, 'aircraft_calls': count, 'first_call': timestamp, 'last_call': timestamp}}
api_tracker_lock = threading.Lock()  # Lock for thread-safe access

# Database instance (initialized in main)
flight_db = None

SSE_KEEPALIVE_INTERVAL = 15  # seconds between keep-alive comments


class SSEClient:
    """Thread-safe wrapper around an SSE client stream."""

    def __init__(self, stream):
        self.stream = stream
        self.lock = threading.Lock()

    def send(self, payload: bytes):
        with self.lock:
            self.stream.write(payload)
            self.stream.flush()

    def send_message(self, data):
        message = f"data: {json.dumps(data)}\n\n".encode('utf-8')
        self.send(message)

    def send_comment(self, comment: str):
        payload = f": {comment}\n\n".encode('utf-8')
        self.send(payload)


def register_sse_client(stream):
    """Register a new SSE client and return current client count."""
    client = SSEClient(stream)
    with sse_clients_lock:
        sse_clients.add(client)
        count = len(sse_clients)
    return client, count


def unregister_sse_client(client):
    """Unregister an SSE client and return remaining client count."""
    with sse_clients_lock:
        sse_clients.discard(client)
        return len(sse_clients)


def broadcast_sse(data):
    """Broadcast JSON data to all SSE clients."""
    with sse_clients_lock:
        if not sse_clients:
            return
        clients = list(sse_clients)

    stale_clients = []

    for client in clients:
        try:
            client.send_message(data)
        except Exception:
            stale_clients.append(client)

    if stale_clients:
        with sse_clients_lock:
            for client in stale_clients:
                sse_clients.discard(client)

def load_config():
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            # Set defaults for map generation if not present
            if 'map_generation' not in config:
                config['map_generation'] = {
                    'enabled': True,
                    'min_interval_seconds': 300,  # 5 minutes
                    'prefer_closest': True,
                    'require_route': True,
                    'min_altitude': 10000,
                    'max_distance_km': 500
                }
            return config
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
    except requests.exceptions.Timeout:
        # Connection timeout - dump1090 might be down or unreachable
        return None
    except requests.exceptions.ConnectionError as e:
        # Connection error - network issue or dump1090 not running
        return None
    except requests.RequestException as e:
        # Other HTTP errors
        return None

def find_best_flight(enriched_flights, config, verbose=False):
    """
    Find the best flight to display based on quality criteria
    
    Criteria (in order of priority):
    1. Has route (origin and destination) if required
    2. Has valid position (lat/lon)
    3. Meets distance and altitude requirements
    4. Closer to receiver (lower distance)
    5. Has complete data (altitude, speed, track)
    6. At reasonable altitude (prefer cruising altitude)
    
    Args:
        enriched_flights: List of enriched flight dictionaries
        config: Configuration dictionary
        verbose: If True, log detailed filtering information
    
    Returns:
        dict: Best flight data or None
    """
    map_config = config.get('map_generation', {})
    require_route = map_config.get('require_route', True)
    max_distance = map_config.get('max_distance_km', 500)
    min_altitude = map_config.get('min_altitude', 10000)
    prefer_closest = map_config.get('prefer_closest', True)
    
    candidates = []
    rejected_reasons = {
        'no_route': 0,
        'no_position': 0,
        'too_far': 0,
        'too_low': 0
    }
    
    for flight in enriched_flights:
        callsign = flight.get('callsign', flight.get('icao', 'Unknown'))
        
        # Must have route if required
        if require_route:
            if not flight.get('origin') or not flight.get('destination'):
                rejected_reasons['no_route'] += 1
                if verbose:
                    print(f"  ❌ {callsign}: No route (origin: {flight.get('origin')}, dest: {flight.get('destination')})")
                continue
        
        # Must have position
        if flight.get('lat') is None or flight.get('lon') is None:
            rejected_reasons['no_position'] += 1
            if verbose:
                print(f"  ❌ {callsign}: No position data")
            continue
        
        # Check distance requirement
        distance = flight.get('distance')
        if distance is not None and distance > max_distance:
            rejected_reasons['too_far'] += 1
            if verbose:
                print(f"  ❌ {callsign}: Too far ({distance:.1f}km > {max_distance}km)")
            continue
        
        # Check altitude requirement
        altitude = flight.get('altitude')
        if altitude is not None and altitude < min_altitude:
            rejected_reasons['too_low'] += 1
            if verbose:
                print(f"  ❌ {callsign}: Too low ({altitude}ft < {min_altitude}ft)")
            continue
        
        # Score the flight (higher is better)
        score = 0
        
        # Distance score (closer is better, max 100 points)
        if distance is not None and prefer_closest:
            # Closer flights get higher scores
            # Within 50km = 100 points, within 100km = 75, within 200km = 50, etc.
            if distance <= 50:
                score += 100
            elif distance <= 100:
                score += 75
            elif distance <= 200:
                score += 50
            elif distance <= 500:
                score += 25
        elif distance is not None:
            # If not preferring closest, just give points for being in range
            score += 50
        
        # Data completeness score (max 60 points)
        if flight.get('altitude') is not None:
            score += 10
        if flight.get('speed') is not None:
            score += 10
        if flight.get('track') is not None or flight.get('heading') is not None:
            score += 10
        if flight.get('aircraft_model') or flight.get('aircraft_type'):
            score += 10
        if flight.get('vertical_rate') is not None:
            score += 10
        if flight.get('origin') and flight.get('destination'):
            score += 10  # Bonus for having route
        
        # Altitude score (prefer cruising altitude, max 30 points)
        if altitude is not None:
            # Prefer flights at cruising altitude (25000-40000 ft)
            if 25000 <= altitude <= 40000:
                score += 30
            elif 15000 <= altitude < 25000 or 40000 < altitude <= 45000:
                score += 15
            elif 10000 <= altitude < 15000:
                score += 5
        
        # Recent data score (max 20 points)
        seen = flight.get('seen', 999)
        if seen <= 10:  # Very recent
            score += 20
        elif seen <= 30:  # Recent
            score += 10
        elif seen <= 60:  # Still acceptable
            score += 5
        
        candidates.append((score, flight))
    
    # Log rejection reasons if no candidates found
    if not candidates and enriched_flights:
        total_flights = len(enriched_flights)
        routes_count = sum(1 for f in enriched_flights if f.get('origin') and f.get('destination'))
        print(f"⚠️  Map generation: No flights meet criteria (total: {total_flights}, with routes: {routes_count})")
        if sum(rejected_reasons.values()) > 0:
            print(f"   Rejected: {rejected_reasons['no_route']} no route, {rejected_reasons['no_position']} no position, "
                  f"{rejected_reasons['too_far']} too far, {rejected_reasons['too_low']} too low")
    
    if not candidates:
        return None
    
    # Return flight with highest score
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_flight = candidates[0]
    
    # Log the selection
    if verbose or len(candidates) > 1:
        print(f"📊 Flight selection: {best_flight.get('callsign', best_flight.get('icao', 'Unknown'))} selected "
              f"(score: {best_score}, distance: {best_flight.get('distance', 'N/A'):.1f}km, "
              f"altitude: {best_flight.get('altitude', 'N/A')}ft) from {len(candidates)} candidates")
    
    return best_flight


def should_generate_map(enriched_flights, config):
    """
    Determine if we should generate a map image for the current flights
    
    Args:
        enriched_flights: List of enriched flight dictionaries
        config: Configuration dictionary
    
    Returns:
        tuple: (should_generate: bool, best_flight: dict or None)
    """
    global last_map_generation_time, last_map_flight_icao
    
    map_config = config.get('map_generation', {})
    
    # Check if map generation is enabled
    if not map_config.get('enabled', True):
        return (False, None)
    
    min_interval = map_config.get('min_interval_seconds', 300)  # Default 5 minutes
    
    # Check if image file exists and how old it is
    map_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inky_ready.png')
    image_exists = os.path.exists(map_file)
    
    # Find best flight candidate with detailed diagnostics
    # Track calls to provide periodic detailed logging
    if not hasattr(should_generate_map, '_call_count'):
        should_generate_map._call_count = 0
    should_generate_map._call_count += 1
    verbose_logging = (should_generate_map._call_count % 20 == 0)  # Every 20th call (~100 seconds)
    
    best_flight = find_best_flight(enriched_flights, config, verbose=verbose_logging)
    if not best_flight:
        # Always log summary when we have flights but no candidates
        if len(enriched_flights) > 0:
            routes_count = sum(1 for f in enriched_flights if f.get('origin') and f.get('destination'))
            positions_count = sum(1 for f in enriched_flights if f.get('lat') and f.get('lon'))
            altitudes = [f.get('altitude') for f in enriched_flights if f.get('altitude') is not None]
            distances = [f.get('distance') for f in enriched_flights if f.get('distance') is not None]
            
            # Log periodic detailed info
            if verbose_logging or should_generate_map._call_count <= 5:  # First 5 calls or every 20th
                print(f"📊 Map generation status: {len(enriched_flights)} flights, {routes_count} with routes, {positions_count} with position")
                if altitudes:
                    print(f"   Altitudes: min={min(altitudes)}ft, max={max(altitudes)}ft (required: >={map_config.get('min_altitude', 10000)}ft)")
                if distances:
                    print(f"   Distances: min={min(distances):.1f}km, max={max(distances):.1f}km (required: <={map_config.get('max_distance_km', 500)}km)")
                if routes_count == 0:
                    print(f"   ⚠️  No flights have routes yet (route lookup may still be in progress)")
        return (False, None)
    
    best_callsign = best_flight.get('callsign', best_flight.get('icao', 'Unknown'))
    
    # If no image exists, generate immediately for first good flight
    if not image_exists:
        print(f"✅ Map generation: Will generate for {best_callsign} (no existing image)")
        return (True, best_flight)
    
    # Check time since last generation
    current_time = time.time()
    if last_map_generation_time is not None:
        time_since_last = current_time - last_map_generation_time
        if time_since_last < min_interval:
            # Too soon, don't generate (log occasionally)
            if verbose_logging:
                print(f"⏸️  Map generation: Skipping {best_callsign} (too soon: {int(time_since_last)}s < {min_interval}s)")
            return (False, None)
    
    # Don't regenerate for the same flight (unless image is very old)
    if best_flight.get('icao') == last_map_flight_icao:
        # Check if image is very old (more than 2x the interval)
        if image_exists:
            image_age = current_time - os.path.getmtime(map_file)
            if image_age < (min_interval * 2):
                print(f"🔄 Map generation: Skipping {best_callsign} (same flight as last, image age: {int(image_age)}s)")
                return (False, None)
            else:
                print(f"✅ Map generation: Will regenerate for {best_callsign} (same flight, but image is very old: {int(image_age)}s)")
                return (True, best_flight)
    
    # Check if image is old enough to warrant regeneration
    if image_exists:
        image_age = current_time - os.path.getmtime(map_file)
        if image_age < min_interval:
            # Image too recent, log occasionally
            if verbose_logging:
                print(f"⏸️  Map generation: Skipping {best_callsign} (image too recent: {int(image_age)}s < {min_interval}s)")
            return (False, None)
    
    # All checks passed - will generate
    image_age = current_time - os.path.getmtime(map_file) if image_exists else 0
    print(f"✅ Map generation: Will generate for {best_callsign} (image age: {int(image_age)}s, "
          f"distance: {best_flight.get('distance', 'N/A'):.1f}km, "
          f"altitude: {best_flight.get('altitude', 'N/A')}ft)")
    return (True, best_flight)


def generate_clear_skies_map(config):
    """
    Generate a "clear skies" map centered on airport or receiver location
    
    Args:
        config: Configuration dictionary
    """
    global last_map_generation_time
    
    clear_skies_config = config.get('clear_skies', {})
    receiver_lat = config.get('receiver_lat')
    receiver_lon = config.get('receiver_lon')
    hide_receiver = config.get('hide_receiver', False)
    
    # Determine location to center on
    target_lat = None
    target_lon = None
    location_name = "Receiver"
    
    # Priority 1: Airport if configured (and hide_receiver is true, or just use airport if configured)
    nearest_airport = clear_skies_config.get('nearest_airport')
    use_airport = False
    
    if hide_receiver:
        # If hiding receiver, always prefer airport
        use_airport = True
    elif nearest_airport:
        # If airport is configured, use it
        use_airport = True
    
    if use_airport and nearest_airport:
        # Try to get airport coordinates
        airport_lat = clear_skies_config.get('airport_lat')
        airport_lon = clear_skies_config.get('airport_lon')
        
        if airport_lat is not None and airport_lon is not None:
            target_lat = airport_lat
            target_lon = airport_lon
            location_name = nearest_airport
        else:
            # Lookup airport coordinates from OpenFlights database
            airport_lat, airport_lon = get_airport_coordinates(nearest_airport)
            if airport_lat is not None and airport_lon is not None:
                target_lat = airport_lat
                target_lon = airport_lon
                location_name = nearest_airport
                # Update config with found coordinates for future use
                clear_skies_config['airport_lat'] = airport_lat
                clear_skies_config['airport_lon'] = airport_lon
            else:
                print(f"⚠️  Warning: Could not find coordinates for airport {nearest_airport}, using receiver location")
                use_airport = False
    
    # Priority 2: Receiver location (if no airport or airport lookup failed)
    if target_lat is None or target_lon is None:
        if receiver_lat is not None and receiver_lon is not None:
            target_lat = receiver_lat
            target_lon = receiver_lon
            
            # If hide_receiver is true and no airport, try to get city name
            if hide_receiver:
                city_name = get_city_name_from_coordinates(receiver_lat, receiver_lon)
                if city_name:
                    location_name = city_name
                else:
                    location_name = "Location"
            else:
                location_name = "Receiver"
        else:
            print("⚠️  Warning: No valid location for clear skies map (no airport or receiver coordinates)")
            return
    
    current_time = time.time()
    
    try:
        # Import the clear skies map generation function
        from map_to_png import generate_clear_skies_map
        
        print(f"🌤️  Generating clear skies map centered on {location_name}...")
        success = generate_clear_skies_map(
            target_lat, 
            target_lon, 
            location_name,
            output_path='inky_ready.png',
            width=800,
            height=480,
            zoom=11,  # Good zoom level for airports/cities
            inky_mode=True  # Always use Inky mode for clear skies
        )
        
        if success:
            last_map_generation_time = current_time
            # Note: generate_clear_skies_map already prints success message, so we don't duplicate it here
            
            # Display the image on Inky display
            map_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inky_ready.png')
            if os.path.exists(map_file) and HAS_INKY_DISPLAY:
                try:
                    print(f"🖥️  Displaying clear skies map on Inky display...")
                    display_success = display_image_on_inky(map_file, verbose=False)
                    if display_success:
                        print(f"✓ Clear skies map displayed on Inky display")
                    else:
                        print(f"⚠️  Warning: Failed to display on Inky (display may not be connected)")
                except Exception as e:
                    print(f"⚠️  Warning: Error displaying on Inky: {e}")
        else:
            print(f"⚠️  Warning: Clear skies map generation failed")
    except Exception as e:
        print(f"⚠️  Warning: Error generating clear skies map: {e}")
        import traceback
        traceback.print_exc()


def generate_map_image(flight_data):
    """
    Generate map image for a flight using map_to_png.py
    
    Args:
        flight_data: Dictionary with flight information
    """
    global last_map_generation_time, last_map_flight_icao, map_generation_in_progress
    
    # Check if map generation is already in progress
    with map_generation_lock:
        if map_generation_in_progress:
            callsign = flight_data.get('callsign', flight_data.get('icao', 'Unknown'))
            print(f"⏸️  Map generation already in progress, skipping {callsign}")
            return
        map_generation_in_progress = True
    
    try:
        # Build command-line arguments for map_to_png.py
        args = [
            'python3', 'map_to_png.py',
            '--lat', str(flight_data.get('lat', 0)),
            '--lon', str(flight_data.get('lon', 0)),
            '--output', 'inky_ready.png',
            '--overlay-card',
            '--inky',  # Use Inky-compatible colors
        ]
        
        # Add optional parameters if available
        if flight_data.get('track') is not None:
            args.extend(['--track', str(flight_data['track'])])
        elif flight_data.get('heading') is not None:
            args.extend(['--track', str(flight_data['heading'])])
        
        if flight_data.get('callsign'):
            args.extend(['--callsign', flight_data['callsign']])
        
        if flight_data.get('origin'):
            args.extend(['--origin', flight_data['origin']])
        
        if flight_data.get('destination'):
            args.extend(['--destination', flight_data['destination']])
        
        if flight_data.get('origin_country'):
            args.extend(['--origin-country', flight_data['origin_country']])
        
        if flight_data.get('destination_country'):
            args.extend(['--destination-country', flight_data['destination_country']])
        
        if flight_data.get('altitude') is not None:
            args.extend(['--altitude', str(flight_data['altitude'])])
        
        if flight_data.get('speed') is not None:
            args.extend(['--speed', str(flight_data['speed'])])
        
        if flight_data.get('vertical_rate') is not None:
            args.extend(['--vertical-rate', str(flight_data['vertical_rate'])])
        
        if flight_data.get('distance') is not None:
            args.extend(['--distance', str(flight_data['distance'])])
        
        if flight_data.get('squawk'):
            args.extend(['--squawk', str(flight_data['squawk'])])
        
        if flight_data.get('icao'):
            args.extend(['--icao', flight_data['icao']])
        
        # Run map generation in background (non-blocking)
        callsign = flight_data.get('callsign', flight_data.get('icao', 'Unknown'))
        print(f"🗺️  Generating map image for flight {callsign}...")
        result = subprocess.run(
            args,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        if result.returncode == 0:
            # Update tracking variables
            last_map_generation_time = time.time()
            last_map_flight_icao = flight_data.get('icao')
            # Note: map_to_png.py already prints success message, so we don't duplicate it here
            
            # Display the image on Inky display
            map_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inky_ready.png')
            if os.path.exists(map_file) and HAS_INKY_DISPLAY:
                try:
                    print(f"🖥️  Displaying map on Inky display...")
                    display_success = display_image_on_inky(map_file, verbose=False)
                    if display_success:
                        print(f"✓ Map displayed on Inky display")
                    else:
                        print(f"⚠️  Warning: Failed to display on Inky (display may not be connected)")
                except Exception as e:
                    print(f"⚠️  Warning: Error displaying on Inky: {e}")
        else:
            error_msg = result.stderr[:200] if result.stderr else result.stdout[:200]
            print(f"⚠️  Warning: Map generation failed for {callsign}: {error_msg}")
    except subprocess.TimeoutExpired:
        callsign = flight_data.get('callsign', flight_data.get('icao', 'Unknown'))
        print(f"⚠️  Warning: Map generation timed out for {callsign}")
    except Exception as e:
        callsign = flight_data.get('callsign', flight_data.get('icao', 'Unknown'))
        print(f"⚠️  Warning: Error generating map image for {callsign}: {e}")
    finally:
        # Always release the lock
        with map_generation_lock:
            map_generation_in_progress = False


def process_aircraft_data(aircraft_data):
    """
    Process raw aircraft data: filter, enrich, and update memory
    
    Returns:
        dict: Enriched flight data ready for broadcasting
    """
    global flight_memory, flight_db
    
    aircraft = aircraft_data.get('aircraft', [])
    
    # NO LONGER filtering out aircraft without callsigns - show ALL aircraft
    # Filter out stale data (seen > 60 seconds ago)
    recent_aircraft = [ac for ac in aircraft if ac.get('seen', 999) <= 60]
    
    # Get receiver position once (cached for performance)
    config = load_config()
    receiver_lat = config.get('receiver_lat')
    receiver_lon = config.get('receiver_lon')
    R = 6371  # Earth radius in km
    
    # Update memory with current flights
    current_icaos = set()
    enriched_flights = []
    
    for ac in recent_aircraft:
        icao = ac.get('hex', 'Unknown')
        callsign = ac.get('flight', '').strip()
        current_icaos.add(icao)
        
        # Get airline info from callsign
        airline_info = get_airline_info(callsign) if callsign else None
        
        # Calculate distance from receiver if we have position
        lat = ac.get('lat')
        lon = ac.get('lon')
        distance = None
        if lat and lon and receiver_lat and receiver_lon:
            try:
                # Haversine distance calculation
                lat1, lon1 = radians(receiver_lat), radians(receiver_lon)
                lat2, lon2 = radians(lat), radians(lon)
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                distance = R * c  # Distance in km
            except:
                pass
        
        # Determine if flight is unidentified (no callsign)
        is_unidentified = not callsign or callsign == ''
        
        # Create enriched flight data
        enriched = {
            'icao': icao,
            'callsign': callsign if callsign else 'Unidentified',
            'altitude': ac.get('alt_baro') or ac.get('altitude'),
            'speed': ac.get('gs'),
            'track': ac.get('track'),
            'heading': ac.get('mag_heading'),  # Magnetic heading (direction nose is pointing)
            'lat': lat,
            'lon': lon,
            'seen': ac.get('seen', 0),
            'timestamp': datetime.now().isoformat(),
            'vertical_rate': ac.get('baro_rate'),  # Rate of climb/descent in ft/min
            'squawk': ac.get('squawk'),  # Transponder code
            'category': ac.get('category'),  # Aircraft category
            'distance': distance,  # Distance from receiver in km
            'unidentified': is_unidentified  # Flag for unidentified flights
        }
        
        # Track flight in new schema (aircraft + flights + positions)
        # This happens AFTER flight_memory is updated with route/aircraft info
        # So we'll do this later in the processing loop
        
        # Add new flights or update existing ones
        if icao not in flight_memory:
            # New flight detected - save event to database
            if flight_db:
                try:
                    config = load_config()
                    if config.get('database', {}).get('save_events', True):
                        flight_db.save_event(icao, 'new_flight', {
                            'callsign': callsign,
                            'lat': lat,
                            'lon': lon,
                            'altitude': ac.get('alt_baro') or ac.get('altitude')
                        })
                except Exception as e:
                    pass  # Don't fail on database errors
            
            # New flight - lookup route info
            flight_memory[icao] = {
                'callsign': callsign,
                'missed_cycles': 0,
                'seen_cycles': 0,
                'origin': None,
                'destination': None,
                'lookup_attempted': False,
                'aircraft_lookup_attempted': False,
                'airline_code': airline_info.get('code') if airline_info else None,
                'airline_logo': airline_info.get('logo_url') if airline_info else None,
                'airline_name': airline_info.get('name') if airline_info else None,
                'aircraft_model': None,
                'aircraft_type': None,
                'aircraft_registration': None
            }
            
            # Lookup route information (only for new flights, requires callsign)
            if callsign and icao != 'Unknown':
                try:
                    flight_memory[icao]['lookup_attempted'] = True
                    lat = ac.get('lat')
                    lon = ac.get('lon')
                    if lat and lon:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        # Track API call
                        with api_tracker_lock:
                            if icao not in api_call_tracker:
                                api_call_tracker[icao] = {'route_calls': 0, 'aircraft_calls': 0, 'first_call': timestamp, 'last_call': timestamp}
                            api_call_tracker[icao]['route_calls'] += 1
                            api_call_tracker[icao]['last_call'] = timestamp
                            call_count = api_call_tracker[icao]['route_calls']
                        print(f"[{timestamp}] 🆕 NEW FLIGHT DETECTED: {callsign} (ICAO: {icao}) - Triggering route API lookup (call #{call_count} for this flight)")
                        route_info = get_flight_route(icao, callsign, lat, lon)
                        if route_info:
                            if route_info.get('error'):
                                flight_memory[icao]['lookup_error'] = route_info.get('error')
                                # Only log errors occasionally to avoid spam
                                if not hasattr(process_aircraft_data, '_route_error_logged'):
                                    process_aircraft_data._route_error_logged = set()
                                if icao not in process_aircraft_data._route_error_logged:
                                    print(f"⚠️  Route lookup error for {callsign}: {route_info.get('error')}")
                                    process_aircraft_data._route_error_logged.add(icao)
                            else:
                                flight_memory[icao]['origin'] = route_info.get('origin')
                                flight_memory[icao]['destination'] = route_info.get('destination')
                                flight_memory[icao]['origin_country'] = route_info.get('origin_country')
                                flight_memory[icao]['destination_country'] = route_info.get('destination_country')
                                flight_memory[icao]['source'] = route_info.get('source', 'unknown')
                                # Log successful route lookup (first time only)
                                if not hasattr(process_aircraft_data, '_route_success_logged'):
                                    process_aircraft_data._route_success_logged = set()
                                if icao not in process_aircraft_data._route_success_logged:
                                    origin = route_info.get('origin', '?')
                                    dest = route_info.get('destination', '?')
                                    print(f"✓ Route found for {callsign}: {origin} → {dest}")
                                    process_aircraft_data._route_success_logged.add(icao)
                                    
                                    # Save event to database
                                    if flight_db:
                                        try:
                                            config = load_config()
                                            if config.get('database', {}).get('save_events', True):
                                                flight_db.save_event(icao, 'route_found', {
                                                    'callsign': callsign,
                                                    'origin': origin,
                                                    'destination': dest,
                                                    'source': route_info.get('source', 'unknown')
                                                })
                                        except Exception as e:
                                            pass  # Don't fail on database errors
                        else:
                            # Route lookup returned None (no route found)
                            flight_memory[icao]['lookup_error'] = 'No route found'
                    else:
                        # No position data yet, will retry later
                        flight_memory[icao]['lookup_error'] = 'No position data'
                except Exception as e:
                    flight_memory[icao]['lookup_error'] = str(e)
                    # Log exceptions occasionally
                    if not hasattr(process_aircraft_data, '_route_exception_logged'):
                        process_aircraft_data._route_exception_logged = set()
                    if icao not in process_aircraft_data._route_exception_logged:
                        print(f"⚠️  Route lookup exception for {callsign}: {e}")
                        process_aircraft_data._route_exception_logged.add(icao)
            
            # Lookup aircraft information (model, type, registration) from adsb.lol
            # This works for ALL flights, with or without callsigns
            if icao != 'Unknown':
                try:
                    flight_memory[icao]['aircraft_lookup_attempted'] = True
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # Track API call
                    with api_tracker_lock:
                        if icao not in api_call_tracker:
                            api_call_tracker[icao] = {'route_calls': 0, 'aircraft_calls': 0, 'first_call': timestamp, 'last_call': timestamp}
                        api_call_tracker[icao]['aircraft_calls'] += 1
                        api_call_tracker[icao]['last_call'] = timestamp
                        call_count = api_call_tracker[icao]['aircraft_calls']
                    display_name = callsign if callsign else 'Unidentified'
                    print(f"[{timestamp}] 🆕 NEW FLIGHT DETECTED: {display_name} (ICAO: {icao}) - Triggering aircraft info API lookup (call #{call_count} for this flight)")
                    aircraft_info = get_aircraft_info_adsblol(icao)
                    if aircraft_info:
                        flight_memory[icao]['aircraft_model'] = aircraft_info.get('model')
                        flight_memory[icao]['aircraft_type'] = aircraft_info.get('type')
                        flight_memory[icao]['aircraft_registration'] = aircraft_info.get('registration')
                        
                        # Save event to database
                        if flight_db:
                            try:
                                config = load_config()
                                if config.get('database', {}).get('save_events', True):
                                    flight_db.save_event(icao, 'aircraft_info_found', aircraft_info)
                            except Exception as e:
                                pass  # Don't fail on database errors
                except Exception as e:
                    pass  # Silently fail - aircraft info is optional
        else:
            flight_memory[icao]['missed_cycles'] = 0  # Reset counter
            flight_memory[icao]['seen_cycles'] = flight_memory[icao].get('seen_cycles', 0) + 1
            
            # Update callsign if it changed
            if callsign and callsign != flight_memory[icao].get('callsign'):
                flight_memory[icao]['callsign'] = callsign
                # Update airline info if callsign changed
                if airline_info:
                    flight_memory[icao]['airline_code'] = airline_info.get('code')
                    flight_memory[icao]['airline_logo'] = airline_info.get('logo_url')
                    flight_memory[icao]['airline_name'] = airline_info.get('name')
            
            # Retry route lookup if:
            # 1. No route info yet AND we have callsign AND position data
            # 2. Previous lookup failed due to missing position AND we now have position
            # 3. On 20th cycle as a retry mechanism (20 seconds since updates are every 1 second)
            needs_route_lookup = (
                not flight_memory[icao].get('origin') and 
                callsign and 
                icao != 'Unknown' and
                lat and lon  # Must have position data
            )
            
            # Check if previous lookup failed due to missing position
            prev_error = flight_memory[icao].get('lookup_error')
            had_no_position = (prev_error == 'No position data')
            
            if needs_route_lookup and (had_no_position or flight_memory[icao]['seen_cycles'] == 20 or not flight_memory[icao].get('lookup_attempted')):
                try:
                    flight_memory[icao]['lookup_attempted'] = True
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    # Track API call
                    with api_tracker_lock:
                        if icao not in api_call_tracker:
                            api_call_tracker[icao] = {'route_calls': 0, 'aircraft_calls': 0, 'first_call': timestamp, 'last_call': timestamp}
                        api_call_tracker[icao]['route_calls'] += 1
                        api_call_tracker[icao]['last_call'] = timestamp
                        call_count = api_call_tracker[icao]['route_calls']
                    retry_reason = "retry (cycle 20)" if flight_memory[icao]['seen_cycles'] == 20 else ("retry (position now available)" if had_no_position else "retry (no previous attempt)")
                    print(f"[{timestamp}] 🔄 RETRY ROUTE LOOKUP: {callsign} (ICAO: {icao}) - Reason: {retry_reason} (call #{call_count} for this flight)")
                    route_info = get_flight_route(icao, callsign, lat, lon)
                    if route_info:
                        if route_info.get('error'):
                            flight_memory[icao]['lookup_error'] = route_info.get('error')
                            # Log errors occasionally
                            if not hasattr(process_aircraft_data, '_route_error_logged'):
                                process_aircraft_data._route_error_logged = set()
                            if icao not in process_aircraft_data._route_error_logged:
                                print(f"⚠️  Route lookup error for {callsign}: {route_info.get('error')}")
                                process_aircraft_data._route_error_logged.add(icao)
                        else:
                            flight_memory[icao]['origin'] = route_info.get('origin')
                            flight_memory[icao]['destination'] = route_info.get('destination')
                            flight_memory[icao]['origin_country'] = route_info.get('origin_country')
                            flight_memory[icao]['destination_country'] = route_info.get('destination_country')
                            flight_memory[icao]['source'] = route_info.get('source', 'unknown')
                            flight_memory[icao]['lookup_error'] = None  # Clear error
                            # Log successful route lookup
                            if not hasattr(process_aircraft_data, '_route_success_logged'):
                                process_aircraft_data._route_success_logged = set()
                            if icao not in process_aircraft_data._route_success_logged:
                                origin = route_info.get('origin', '?')
                                dest = route_info.get('destination', '?')
                                print(f"✓ Route found for {callsign}: {origin} → {dest}")
                                process_aircraft_data._route_success_logged.add(icao)
                    else:
                        # Route lookup returned None
                        flight_memory[icao]['lookup_error'] = 'No route found'
                except Exception as e:
                    flight_memory[icao]['lookup_error'] = str(e)
                    # Log exceptions occasionally
                    if not hasattr(process_aircraft_data, '_route_exception_logged'):
                        process_aircraft_data._route_exception_logged = set()
                    if icao not in process_aircraft_data._route_exception_logged:
                        print(f"⚠️  Route lookup exception for {callsign}: {e}")
                        process_aircraft_data._route_exception_logged.add(icao)
        
        # Add memory data to enriched flight
        if icao in flight_memory:
            # Set status: unidentified takes priority, then saved/new based on cycles
            if is_unidentified:
                enriched['status'] = 'unidentified'
            else:
                enriched['status'] = 'saved' if flight_memory[icao].get('seen_cycles', 0) > 0 else 'new'
            enriched['seen_cycles'] = flight_memory[icao].get('seen_cycles', 0)
            enriched['origin'] = flight_memory[icao].get('origin')
            enriched['destination'] = flight_memory[icao].get('destination')
            enriched['origin_country'] = flight_memory[icao].get('origin_country')
            enriched['destination_country'] = flight_memory[icao].get('destination_country')
            enriched['route_source'] = flight_memory[icao].get('source')
            enriched['aircraft_model'] = flight_memory[icao].get('aircraft_model')
            enriched['aircraft_type'] = flight_memory[icao].get('aircraft_type')
            enriched['aircraft_registration'] = flight_memory[icao].get('aircraft_registration')
            enriched['lookup_error'] = flight_memory[icao].get('lookup_error')
            # Add lat/lon from current aircraft data (already in enriched from above)
            # They're already in enriched from the basic flight data, so we're good
            
            # Include airline info from memory (or compute if not stored)
            if flight_memory[icao].get('airline_logo'):
                enriched['airline_code'] = flight_memory[icao].get('airline_code')
                enriched['airline_logo'] = flight_memory[icao].get('airline_logo')
                enriched['airline_name'] = flight_memory[icao].get('airline_name')
            elif airline_info:
                # Store it for future use
                flight_memory[icao]['airline_code'] = airline_info.get('code')
                flight_memory[icao]['airline_logo'] = airline_info.get('logo_url')
                flight_memory[icao]['airline_name'] = airline_info.get('name')
                enriched['airline_code'] = airline_info.get('code')
                enriched['airline_logo'] = airline_info.get('logo_url')
                enriched['airline_name'] = airline_info.get('name')
        else:
            # Set status: unidentified takes priority
            enriched['status'] = 'unidentified' if is_unidentified else 'new'
            # Add airline logo info if available (for new flights)
            if airline_info:
                enriched['airline_code'] = airline_info.get('code')
                enriched['airline_logo'] = airline_info.get('logo_url')
                enriched['airline_name'] = airline_info.get('name')
        
        # Track flight in new schema (aircraft + flights + positions)
        # This happens AFTER enriched data is fully populated
        if flight_db:
            try:
                # Update aircraft record with info from flight_memory
                aircraft_info = {
                    'registration': enriched.get('aircraft_registration'),
                    'type': enriched.get('aircraft_type'),
                    'model': enriched.get('aircraft_model'),
                    'manufacturer': None  # Add if available
                }
                flight_db.upsert_aircraft(icao, aircraft_info)
                
                # Get or create active flight
                active_flight = flight_db.get_active_flight(icao)
                
                if not active_flight:
                    # Start new flight
                    flight_info = {
                        'origin': enriched.get('origin'),
                        'destination': enriched.get('destination'),
                        'origin_country': enriched.get('origin_country'),
                        'destination_country': enriched.get('destination_country'),
                        'airline_code': enriched.get('airline_code'),
                        'airline_name': enriched.get('airline_name')
                    }
                    flight_id = flight_db.start_flight(icao, callsign, flight_info)
                    flight_db.log_flight_event(flight_id, 'new_flight', {
                        'callsign': callsign,
                        'altitude': enriched.get('altitude')
                    }, aircraft_icao=icao)
                else:
                    flight_id = active_flight['id']
                    active_callsign = active_flight.get('callsign')
                    
                    # Check if callsign changed (indicates new flight)
                    # Cases to handle:
                    # 1. Active flight has no callsign, new callsign arrives -> new flight
                    # 2. Active flight has callsign A, new callsign B arrives -> new flight
                    # 3. Active flight has callsign, new data has no callsign -> keep existing
                    # 4. Both have same callsign -> update existing flight
                    callsign_changed = False
                    if callsign:
                        # We have a callsign in new data
                        if not active_callsign:
                            # Active flight has no callsign, but we now have one -> new flight
                            callsign_changed = True
                        elif callsign != active_callsign:
                            # Both have callsigns but they're different -> new flight
                            callsign_changed = True
                    
                    if callsign_changed:
                        # End old flight, start new one
                        flight_db.end_flight(flight_id, 'callsign_change')
                        flight_db.log_flight_event(flight_id, 'callsign_change', {
                            'old_callsign': active_callsign,
                            'new_callsign': callsign
                        }, aircraft_icao=icao)
                        
                        flight_info = {
                            'origin': enriched.get('origin'),
                            'destination': enriched.get('destination'),
                            'origin_country': enriched.get('origin_country'),
                            'destination_country': enriched.get('destination_country'),
                            'airline_code': enriched.get('airline_code'),
                            'airline_name': enriched.get('airline_name')
                        }
                        flight_id = flight_db.start_flight(icao, callsign, flight_info)
                    else:
                        # Update flight info if we learned new details
                        mem = flight_memory.get(icao, {})
                        if mem.get('origin') or mem.get('destination'):
                            flight_info = {
                                'origin': mem.get('origin'),
                                'destination': mem.get('destination'),
                                'origin_country': mem.get('origin_country'),
                                'destination_country': mem.get('destination_country'),
                                'airline_code': mem.get('airline_code'),
                                'airline_name': mem.get('airline_name')
                            }
                            flight_db.update_flight_info(flight_id, flight_info)
                
                # Insert position (only if we have valid coordinates)
                if enriched.get('lat') is not None and enriched.get('lon') is not None:
                    flight_db.insert_position(flight_id, enriched)
                
            except Exception as e:
                # Don't fail on database errors, just log them once per ICAO
                if not hasattr(process_aircraft_data, '_db_error_logged'):
                    process_aircraft_data._db_error_logged = set()
                if icao not in process_aircraft_data._db_error_logged:
                    print(f"⚠️  Flight tracking error for {icao}: {e}")
                    process_aircraft_data._db_error_logged.add(icao)
        
        enriched_flights.append(enriched)
    
    # Add dummy flight for testing (if enabled in config)
    config = load_config()
    receiver_lat = config.get('receiver_lat', 52.40585)
    receiver_lon = config.get('receiver_lon', 13.55214)
    show_test_flight = config.get('show_test_flight', False)
    
    dummy_icao = 'TEST01'
    
    # Only add test flight if enabled in config
    if show_test_flight:
        if dummy_icao not in flight_memory:
            # Initialize dummy flight in memory
            flight_memory[dummy_icao] = {
                'callsign': 'TEST123',
                'missed_cycles': 0,
                'seen_cycles': 0,
                'origin': 'BER',
                'destination': 'CDG',
                'origin_country': 'Germany',
                'destination_country': 'France',
                'lookup_attempted': True,
                'aircraft_lookup_attempted': True,
                'airline_code': 'TEST',
                'airline_logo': None,
                'airline_name': 'Test Airline',
                'aircraft_model': 'B737-800',
                'aircraft_type': 'B738',
                'aircraft_registration': 'TEST-001'
            }
        else:
            flight_memory[dummy_icao]['seen_cycles'] += 1
        
        # Create dummy flight enriched data
        dummy_lat = receiver_lat + 0.02  # 2km north
        dummy_lon = receiver_lon + 0.02  # 2km east
        dummy_distance = 2.8  # Approximately 2.8 km away
        
        dummy_enriched = {
            'icao': dummy_icao,
            'callsign': 'TEST123',
            'altitude': 35000,
            'speed': 450.5,
            'track': 87.6,
            'heading': 87.6,
            'lat': dummy_lat,
            'lon': dummy_lon,
            'seen': 0,
            'timestamp': datetime.now().isoformat(),
            'vertical_rate': 500,
            'squawk': '1234',
            'category': None,
            'distance': dummy_distance,
            'status': 'saved',
            'seen_cycles': flight_memory[dummy_icao].get('seen_cycles', 0),
            'origin': flight_memory[dummy_icao].get('origin'),
            'destination': flight_memory[dummy_icao].get('destination'),
            'origin_country': flight_memory[dummy_icao].get('origin_country'),
            'destination_country': flight_memory[dummy_icao].get('destination_country'),
            'route_source': 'test',
            'aircraft_model': flight_memory[dummy_icao].get('aircraft_model'),
            'aircraft_type': flight_memory[dummy_icao].get('aircraft_type'),
            'aircraft_registration': flight_memory[dummy_icao].get('aircraft_registration'),
            'lookup_error': None,
            'airline_code': flight_memory[dummy_icao].get('airline_code'),
            'airline_logo': flight_memory[dummy_icao].get('airline_logo'),
            'airline_name': flight_memory[dummy_icao].get('airline_name')
        }
        
        enriched_flights.append(dummy_enriched)
        current_icaos.add(dummy_icao)  # Mark dummy flight as seen
    else:
        # Remove test flight from memory if it exists and test flight is disabled
        if dummy_icao in flight_memory:
            del flight_memory[dummy_icao]
        # Also remove it from current_icaos if it was added
        current_icaos.discard(dummy_icao)
    
    # Increment missed cycles for flights not seen (except dummy flight if enabled)
    test_icao_exception = dummy_icao if show_test_flight else None
    for icao in flight_memory:
        if icao not in current_icaos and icao != test_icao_exception:
            flight_memory[icao]['missed_cycles'] += 1
    
    # Remove flights that have been missing for 10 cycles (except dummy flight if enabled)
    flights_to_remove = [icao for icao, info in flight_memory.items() 
                       if info['missed_cycles'] >= 10 and icao != test_icao_exception]
    for icao in flights_to_remove:
        del flight_memory[icao]
    
    # Calculate statistics
    stats = {
        'active': len(enriched_flights),
        'with_callsigns': len([ac for ac in recent_aircraft if ac.get('flight', '').strip()]),
        'total': len(aircraft),
        'timestamp': datetime.now().isoformat()
    }
    
    # Include receiver position for map
    config = load_config()
    stats['receiver_lat'] = config.get('receiver_lat')
    stats['receiver_lon'] = config.get('receiver_lon')
    stats['hide_receiver'] = config.get('hide_receiver', False)
    clear_skies_config = config.get('clear_skies', {})
    stats['nearest_airport'] = clear_skies_config.get('nearest_airport')
    stats['nearest_airport_lat'] = clear_skies_config.get('airport_lat')
    stats['nearest_airport_lon'] = clear_skies_config.get('airport_lon')
    
    # Check if we should generate a map image
    should_gen, best_flight = should_generate_map(enriched_flights, config)
    if should_gen and best_flight:
        # Generate map in background thread (non-blocking)
        map_thread = threading.Thread(
            target=generate_map_image,
            args=(best_flight,),
            daemon=True
        )
        map_thread.start()
    
    return {
        'type': 'flight_update',
        'timestamp': datetime.now().isoformat(),
        'stats': stats,
        'flights': enriched_flights,
        'flight_count': len(enriched_flights)
    }
# HTTP server
class FlightHTTPHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.path.dirname(__file__), 'web'), **kwargs)

    def do_GET(self):
        if self.path == '/events':
            self.handle_sse()
        elif self.path == '/api/replay/stats':
            self.handle_replay_stats()
        elif self.path.startswith('/api/replay/stream'):
            self.handle_replay_stream()
        elif self.path.startswith('/api/replay'):
            self.handle_replay_api()
        elif self.path.startswith('/api/flights'):
            self.handle_flights_api()
        elif self.path.startswith('/api/aircraft'):
            self.handle_aircraft_api()
        else:
            super().do_GET()
    
    def handle_replay_stats(self):
        """Handle replay stats request - returns metadata only, no flight data"""
        try:
            # Get database instance
            global flight_db
            if not flight_db:
                config = load_config()
                db_config = config.get('database', {})
                if db_config.get('enabled', False):
                    db_path = db_config.get('db_path', 'flights.db')
                    if not os.path.exists(db_path):
                        self.send_response(503)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Database file not found',
                            'message': f'Database file "{db_path}" does not exist.'
                        }).encode())
                        return
                    flight_db = FlightDatabase(db_path)
                else:
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Database not enabled',
                        'message': 'Database is not enabled in config.json.'
                    }).encode())
                    return
            
            # Get stats only (no flight data)
            stats = flight_db.get_database_stats()
            
            # Get sample timestamps to verify data exists
            sample_timestamps = []
            sample_flight_count = 0
            try:
                with flight_db.lock:
                    import sqlite3
                    conn = sqlite3.connect(flight_db.db_path)
                    cursor = conn.cursor()
                    
                    # Get a few sample timestamps
                    cursor.execute('''
                        SELECT DISTINCT timestamp, COUNT(*) as flight_count
                        FROM flight_snapshots
                        GROUP BY timestamp
                        ORDER BY timestamp
                        LIMIT 5
                    ''')
                    samples = cursor.fetchall()
                    for ts, count in samples:
                        sample_timestamps.append({'timestamp': ts, 'flight_count': count})
                        sample_flight_count += count
                    
                    # Count flights with position data
                    cursor.execute('''
                        SELECT COUNT(*) FROM flight_snapshots
                        WHERE lat IS NOT NULL AND lon IS NOT NULL
                    ''')
                    flights_with_pos = cursor.fetchone()[0]
                    
                    conn.close()
            except Exception as e:
                print(f"⚠️  Error getting sample data: {e}")
                flights_with_pos = 0
            
            response = {
                'available_range': {
                    'min_date': stats.get('min_date'),
                    'max_date': stats.get('max_date')
                },
                'total_snapshots': stats.get('snapshot_count', 0),
                'unique_flights': stats.get('unique_flights', 0),
                'database_size_mb': stats.get('database_size_mb', 0),
                'flights_with_position': flights_with_pos,
                'sample_timestamps': sample_timestamps
            }
            
            print(f"📊 Stats response: {stats.get('snapshot_count', 0)} snapshots, {flights_with_pos} flights with position")
            if sample_timestamps:
                print(f"   Sample timestamps: {sample_timestamps[0]['timestamp']} ({sample_timestamps[0]['flight_count']} flights)")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Replay stats error: {error_msg}")
            print(traceback.format_exc())
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': error_msg}).encode())
    
    def handle_replay_stream(self):
        """Handle SSE stream for replay playback"""
        from urllib.parse import urlparse, parse_qs
        
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            
            start_timestamp = params.get('start', [None])[0]
            speed = float(params.get('speed', ['1'])[0])  # Playback speed multiplier
            
            if not start_timestamp:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing start parameter'}).encode())
                return
            
            # Get database instance
            global flight_db
            if not flight_db:
                config = load_config()
                db_config = config.get('database', {})
                if db_config.get('enabled', False):
                    db_path = db_config.get('db_path', 'flights.db')
                    flight_db = FlightDatabase(db_path)
                else:
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Database not enabled'}).encode())
                    return
            
            # Set up SSE headers
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            # Normalize start timestamp
            from datetime import datetime, timedelta
            try:
                if '.' in start_timestamp or '+' in start_timestamp or start_timestamp.endswith('Z'):
                    dt = datetime.fromisoformat(start_timestamp.replace('Z', '+00:00'))
                    current_timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    dt = datetime.strptime(start_timestamp, '%Y-%m-%dT%H:%M:%S')
                    current_timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S')
            except Exception as e:
                self.wfile.write(f"data: {json.dumps({'error': f'Invalid timestamp format: {e}'})}\n\n".encode())
                return
            
            # Get available range
            stats = flight_db.get_database_stats()
            max_date = stats.get('max_date')
            if max_date:
                max_dt = datetime.fromisoformat(max_date.replace('Z', '+00:00'))
            else:
                max_dt = None
            
            # Stream snapshots
            print(f"📡 Starting replay stream from {current_timestamp} at {speed}x speed")
            
            # Get list of actual timestamps that exist in the database (for smooth playback)
            with flight_db.lock:
                import sqlite3
                conn = sqlite3.connect(flight_db.db_path)
                cursor = conn.cursor()
                
                # Find the starting timestamp index
                cursor.execute('''
                    SELECT DISTINCT timestamp
                    FROM flight_snapshots
                    WHERE timestamp >= ?
                    ORDER BY timestamp
                ''', (current_timestamp,))
                available_timestamps = [row[0] for row in cursor.fetchall()]
                conn.close()
            
            if not available_timestamps:
                print(f"   ⚠️  No snapshots found starting from {current_timestamp}")
                end_data = {'type': 'end', 'message': 'No data available from this timestamp'}
                self.wfile.write(f"data: {json.dumps(end_data)}\n\n".encode('utf-8'))
                self.wfile.flush()
                return
            
            print(f"   📊 Found {len(available_timestamps)} snapshots to replay")
            timestamp_index = 0
            
            try:
                while timestamp_index < len(available_timestamps):
                    # Use actual timestamp from database (not incremented by 1 second)
                    current_timestamp = available_timestamps[timestamp_index]
                    
                    # Get flights for current timestamp
                    flights = flight_db.get_flights_at_time(current_timestamp, tolerance_seconds=1)
                    
                    # Note: Since we're using actual timestamps from the database,
                    # we should always have flights. If not, it's likely a data issue.
                    if len(flights) == 0 and timestamp_index < 3:
                        print(f"   ⚠️  No flights found at timestamp {current_timestamp} (index {timestamp_index})")
                    
                    # Convert to flight format
                    flight_data = []
                    for row in flights:
                        lat = row.get('lat')
                        lon = row.get('lon')
                        if lat is not None:
                            try:
                                lat = float(lat)
                            except (ValueError, TypeError):
                                lat = None
                        if lon is not None:
                            try:
                                lon = float(lon)
                            except (ValueError, TypeError):
                                lon = None
                        
                        flight = {
                            'icao': row.get('icao'),
                            'callsign': row.get('callsign') or 'Unidentified',
                            'lat': lat,
                            'lon': lon,
                            'altitude': row.get('altitude'),
                            'speed': row.get('speed'),
                            'track': row.get('track'),
                            'heading': row.get('heading'),
                            'vertical_rate': row.get('vertical_rate'),
                            'squawk': row.get('squawk'),
                            'distance': row.get('distance'),
                            'origin': row.get('origin'),
                            'destination': row.get('destination'),
                            'origin_country': row.get('origin_country'),
                            'destination_country': row.get('destination_country'),
                            'aircraft_model': row.get('aircraft_model'),
                            'aircraft_type': row.get('aircraft_type'),
                            'aircraft_registration': row.get('aircraft_registration'),
                            'airline_code': row.get('airline_code'),
                            'airline_name': row.get('airline_name'),
                            'status': row.get('status') or ('unidentified' if row.get('unidentified') else 'saved'),
                            'unidentified': bool(row.get('unidentified')),
                            'timestamp': row.get('timestamp')
                        }
                        flight_data.append(flight)
                    
                    # Count flights with position
                    flights_with_pos = len([f for f in flight_data if f.get('lat') is not None and f.get('lon') is not None])
                    
                    # Send snapshot
                    snapshot_data = {
                        'type': 'snapshot',
                        'timestamp': current_timestamp,
                        'flights': flight_data,
                        'count': len(flight_data)
                    }
                    
                    if timestamp_index < 3 or timestamp_index % 50 == 0:  # Log first 3 and every 50th
                        print(f"   📤 Snapshot {timestamp_index + 1}/{len(available_timestamps)}: {len(flight_data)} flights ({flights_with_pos} with position) at {current_timestamp}")
                    
                    message = f"data: {json.dumps(snapshot_data)}\n\n"
                    self.wfile.write(message.encode('utf-8'))
                    self.wfile.flush()
                    
                    # Move to next timestamp
                    timestamp_index += 1
                    
                    # Check if we've reached the end
                    if timestamp_index >= len(available_timestamps):
                        # Send end signal
                        end_data = {'type': 'end', 'message': 'Reached end of available data'}
                        self.wfile.write(f"data: {json.dumps(end_data)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                        break
                    
                    # Calculate sleep time based on actual time difference between snapshots
                    if timestamp_index < len(available_timestamps):
                        next_timestamp = available_timestamps[timestamp_index]
                        try:
                            # Parse timestamps (handle microseconds)
                            if '.' in current_timestamp:
                                current_dt = datetime.fromisoformat(current_timestamp.replace('Z', '+00:00'))
                            else:
                                current_dt = datetime.strptime(current_timestamp, '%Y-%m-%dT%H:%M:%S')
                            
                            if '.' in next_timestamp:
                                next_dt = datetime.fromisoformat(next_timestamp.replace('Z', '+00:00'))
                            else:
                                next_dt = datetime.strptime(next_timestamp, '%Y-%m-%dT%H:%M:%S')
                            
                            time_diff = (next_dt - current_dt).total_seconds()
                            
                            # Sleep based on actual time difference, adjusted for playback speed
                            # This makes playback smooth - if snapshots are 6 seconds apart, we wait 6/speed seconds
                            sleep_time = max(0.05, time_diff / speed)  # Min 50ms to prevent too fast updates
                            time.sleep(sleep_time)
                        except Exception as e:
                            # Fallback to 1 second if timestamp parsing fails
                            print(f"   ⚠️  Error calculating sleep time: {e}, using 1s fallback")
                            time.sleep(1.0 / speed)
                    
            except BrokenPipeError:
                # Client disconnected
                print("📡 Replay stream client disconnected")
            except Exception as e:
                print(f"⚠️  Replay stream error: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Replay stream setup error: {error_msg}")
            print(traceback.format_exc())
            try:
                self.wfile.write(f"data: {json.dumps({'error': error_msg})}\n\n".encode())
                self.wfile.flush()
            except:
                pass
    
    def handle_replay_api(self):
        """Handle replay API requests for historical flight data"""
        from urllib.parse import urlparse, parse_qs
        
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            
            timestamp = params.get('timestamp', [None])[0]
            start_time = params.get('start_time', [None])[0]
            end_time = params.get('end_time', [None])[0]
            icao = params.get('icao', [None])[0]
            
            # Get database instance
            global flight_db
            if not flight_db:
                # Try to initialize database if not already initialized
                config = load_config()
                db_config = config.get('database', {})
                if db_config.get('enabled', False):
                    db_path = db_config.get('db_path', 'flights.db')
                    try:
                        # Check if database file exists
                        if not os.path.exists(db_path):
                            self.send_response(503)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({
                                'error': 'Database file not found',
                                'message': f'Database file "{db_path}" does not exist. The database will be created when flight data is collected.'
                            }).encode())
                            return
                        flight_db = FlightDatabase(db_path)
                    except Exception as e:
                        self.send_response(503)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Database initialization failed',
                            'message': str(e)
                        }).encode())
                        return
                else:
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Database not enabled',
                        'message': 'Database is not enabled in config.json. Set "database.enabled" to true to use replay functionality.'
                    }).encode())
                    return
            
            # Get database stats first (needed for available_range in response)
            stats = flight_db.get_database_stats()
            
            # Query database based on parameters
            flights = []
            if timestamp:
                # Normalize timestamp format - fix malformed timestamps like "20:34:00:00"
                try:
                    from datetime import datetime
                    original_timestamp = timestamp
                    
                    # Fix malformed timestamps with extra colons (e.g., "2025-12-17T20:34:00:00")
                    if 'T' in timestamp:
                        parts = timestamp.split('T')
                        if len(parts) == 2:
                            date_part = parts[0]
                            time_part = parts[1]
                            
                            # Split time part and take only first 3 components (HH:MM:SS)
                            time_parts = time_part.split(':')
                            if len(time_parts) > 3:
                                # Has extra components, take only HH:MM:SS
                                time_parts = time_parts[:3]
                                # Remove any trailing empty strings
                                time_parts = [p for p in time_parts if p]
                                # Ensure we have exactly 3 parts
                                while len(time_parts) < 3:
                                    time_parts.append('00')
                                time_part = ':'.join(time_parts[:3])
                            
                            timestamp = f"{date_part}T{time_part}"
                    
                    # Remove microseconds and timezone if present
                    if '.' in timestamp:
                        timestamp = timestamp.split('.')[0]
                    if '+' in timestamp:
                        timestamp = timestamp.split('+')[0]
                    if timestamp.endswith('Z'):
                        timestamp = timestamp[:-1]
                    
                    # Validate and normalize format
                    try:
                        dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
                        timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        # If parsing fails, try ISO format
                        try:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S')
                        except:
                            print(f"⚠️  Could not parse timestamp: {original_timestamp}")
                    
                    if original_timestamp != timestamp:
                        print(f"🔧 Normalized timestamp: {original_timestamp} -> {timestamp}")
                    print(f"🔍 Replay query: timestamp={timestamp}")
                except Exception as e:
                    print(f"⚠️  Error parsing timestamp {timestamp}: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Get flights at specific timestamp (or closest match within 5 seconds)
                # Use larger tolerance since database timestamps have microseconds
                flights = flight_db.get_flights_at_time(timestamp, tolerance_seconds=5)
                print(f"📊 Found {len(flights)} flights for timestamp {timestamp}")
                
                # Debug: Show sample flight data if available
                if flights:
                    sample = flights[0]
                    print(f"   Sample flight: ICAO={sample.get('icao')}, callsign={sample.get('callsign')}, lat={sample.get('lat')}, lon={sample.get('lon')}")
                else:
                    print(f"   ⚠️  No flights found for this timestamp")
            elif start_time and end_time:
                # Limit range queries to prevent huge responses
                # Only allow small ranges (max 1 hour) or require icao filter
                from datetime import datetime
                try:
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    duration = (end_dt - start_dt).total_seconds()
                    
                    # If no ICAO filter and range > 1 hour, reject
                    if not icao and duration > 3600:
                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Range too large',
                            'message': 'Time range queries without ICAO filter are limited to 1 hour. Use /api/replay/stream for longer ranges.'
                        }).encode())
                        return
                except:
                    pass  # If parsing fails, continue (will fail later anyway)
                
                # Get flights in time range
                if icao:
                    flights = flight_db.get_flight_history(icao, start_time, end_time)
                else:
                    flights = flight_db.get_flights_by_time_range(start_time, end_time)
            else:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing required parameters'}).encode())
                return
            
            # Limit response size for single timestamp queries (prevent huge responses)
            max_flights_per_response = 200
            if len(flights) > max_flights_per_response:
                print(f"⚠️  Limiting response to {max_flights_per_response} flights (found {len(flights)})")
                flights = flights[:max_flights_per_response]
            
            # Convert database rows to flight format
            flight_data = []
            flights_with_position = 0
            for row in flights:
                # Convert None/null values to null (JSON null)
                lat = row.get('lat')
                lon = row.get('lon')
                
                # Handle SQLite NULL values (which come through as None in Python)
                if lat is not None:
                    try:
                        lat = float(lat)
                    except (ValueError, TypeError):
                        lat = None
                if lon is not None:
                    try:
                        lon = float(lon)
                    except (ValueError, TypeError):
                        lon = None
                
                if lat is not None and lon is not None:
                    flights_with_position += 1
                
                flight = {
                    'icao': row.get('icao'),
                    'callsign': row.get('callsign') or 'Unidentified',
                    'lat': lat,
                    'lon': lon,
                    'altitude': row.get('altitude'),
                    'speed': row.get('speed'),
                    'track': row.get('track'),
                    'heading': row.get('heading'),
                    'vertical_rate': row.get('vertical_rate'),
                    'squawk': row.get('squawk'),
                    'distance': row.get('distance'),
                    'origin': row.get('origin'),
                    'destination': row.get('destination'),
                    'origin_country': row.get('origin_country'),
                    'destination_country': row.get('destination_country'),
                    'aircraft_model': row.get('aircraft_model'),
                    'aircraft_type': row.get('aircraft_type'),
                    'aircraft_registration': row.get('aircraft_registration'),
                    'airline_code': row.get('airline_code'),
                    'airline_name': row.get('airline_name'),
                    'status': row.get('status') or ('unidentified' if row.get('unidentified') else 'saved'),
                    'unidentified': bool(row.get('unidentified')),
                    'timestamp': row.get('timestamp')
                }
                flight_data.append(flight)
            
            print(f"   📍 {flights_with_position} of {len(flight_data)} flights have position data")
            
            # Stats already retrieved above if timestamp query, otherwise get them now
            if not 'stats' in locals():
                stats = flight_db.get_database_stats()
            
            # Debug: log what we're returning
            print(f"📤 Replay API response: {len(flight_data)} flights")
            print(f"   Available range: {stats.get('min_date')} to {stats.get('max_date')}")
            print(f"   Total snapshots in DB: {stats.get('snapshot_count', 0)}")
            print(f"   Response size: ~{len(json.dumps(flight_data))} bytes")
            
            # If no flights found, provide helpful message
            if len(flight_data) == 0:
                print(f"   ⚠️  No flights found. Query was for timestamp: {timestamp or start_time}")
                if stats.get('snapshot_count', 0) == 0:
                    print(f"   ℹ️  Database appears to be empty - no snapshots saved yet")
                else:
                    print(f"   ℹ️  Database has {stats.get('snapshot_count', 0)} snapshots but none match the requested time")
            
            response = {
                'flights': flight_data,
                'count': len(flight_data),
                'timestamp': timestamp or start_time,
                'available_range': {
                    'min_date': stats.get('min_date'),
                    'max_date': stats.get('max_date')
                },
                'total_snapshots': stats.get('snapshot_count', 0)
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Replay API error: {error_msg}")
            print(traceback.format_exc())
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': error_msg}).encode())
    
    def handle_flights_api(self):
        """Handle flights API requests"""
        from urllib.parse import urlparse, parse_qs
        import re
        
        try:
            print(f"📡📡📡 Flights API request received: {self.path}")
            print(f"   Request method: {self.command}")
            print(f"   Client: {self.client_address}")
            
            # Quick test: return immediately without database
            if '?test=1' in self.path:
                print(f"   ✓ Test endpoint - returning immediately")
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'test': 'ok', 'message': 'Server is responding'}).encode())
                print(f"   ✓ Test response sent")
                return
            
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            print(f"   Parsed path: {parsed.path}, query: {parsed.query}")
            
            # Parse path: /api/flights/{id}/positions or /api/flights/{id} or /api/flights
            path_parts = parsed.path.strip('/').split('/')
            print(f"   Path parts: {path_parts}")
            
            # Get database instance
            global flight_db
            print(f"   Checking flight_db: {flight_db is not None}")
            if not flight_db:
                config = load_config()
                db_config = config.get('database', {})
                if db_config.get('enabled', False):
                    db_path = db_config.get('db_path', 'flights.db')
                    if not os.path.exists(db_path):
                        self.send_response(503)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Database not enabled',
                            'message': f'Database file "{db_path}" does not exist.'
                        }).encode())
                        return
                    flight_db = FlightDatabase(db_path)
                else:
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Database not enabled',
                        'message': 'Database is disabled in config.json'
                    }).encode())
                    return
            
            # Route: /api/flights/{id}/map (static map image)
            if len(path_parts) >= 4 and path_parts[2].isdigit() and path_parts[3] == 'map':
                flight_id = int(path_parts[2])
                print(f"   🗺️  Handling map image request for flight {flight_id}")
                
                # Get flight positions
                positions = flight_db.get_flight_positions(flight_id, limit=None)
                if not positions or len(positions) == 0:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'No positions found',
                        'message': f'Flight #{flight_id} has no position data'
                    }).encode())
                    return
                
                # Filter valid positions
                valid_positions = [p for p in positions if p.get('lat') is not None and p.get('lon') is not None]
                if len(valid_positions) == 0:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'No valid positions',
                        'message': f'Flight #{flight_id} has no valid coordinates'
                    }).encode())
                    return
                
                # Calculate bounds for the flight path
                lats = [p['lat'] for p in valid_positions]
                lons = [p['lon'] for p in valid_positions]
                min_lat, max_lat = min(lats), max(lats)
                min_lon, max_lon = min(lons), max(lons)
                
                # Center and zoom calculation
                center_lat = (min_lat + max_lat) / 2
                center_lon = (min_lon + max_lon) / 2
                
                # Calculate appropriate zoom level based on bounds
                lat_range = max_lat - min_lat
                lon_range = max_lon - min_lon
                max_range = max(lat_range, lon_range)
                
                # Determine zoom level (rough calculation)
                if max_range > 10:
                    zoom = 6
                elif max_range > 5:
                    zoom = 7
                elif max_range > 2:
                    zoom = 8
                elif max_range > 1:
                    zoom = 9
                elif max_range > 0.5:
                    zoom = 10
                elif max_range > 0.2:
                    zoom = 11
                else:
                    zoom = 12
                
                # Import map generation function
                try:
                    from map_to_png import generate_osm_map_png, deg2num, num2deg
                    from PIL import Image, ImageDraw
                    import tempfile
                    import math
                    from io import BytesIO
                    
                    # Generate map centered on flight path
                    # Use center of bounds as the center point
                    flight_data = {
                        'lat': center_lat,
                        'lon': center_lon
                    }
                    
                    # Generate map to temporary file
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                        tmp_path = tmp_file.name
                    
                    # Generate base map (600x300 for mini-map)
                    width = 600
                    height = 300
                    success = generate_osm_map_png(flight_data, tmp_path, width=width, height=height, zoom=zoom, overlay_card=False)
                    
                    if not success:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Map generation failed',
                            'message': 'Could not generate map image'
                        }).encode())
                        return
                    
                    # Read the generated image and draw flight path
                    img = Image.open(tmp_path)
                    draw = ImageDraw.Draw(img)
                    
                    # Calculate bounds with padding for better visualization
                    lat_padding = (max_lat - min_lat) * 0.1
                    lon_padding = (max_lon - min_lon) * 0.1
                    bounds_min_lat = min_lat - lat_padding
                    bounds_max_lat = max_lat + lat_padding
                    bounds_min_lon = min_lon - lon_padding
                    bounds_max_lon = max_lon + lon_padding
                    
                    # Convert positions to pixel coordinates
                    def latlon_to_pixel(lat, lon):
                        # Simple linear mapping (good enough for small areas)
                        x = int((lon - bounds_min_lon) / (bounds_max_lon - bounds_min_lon) * width)
                        y = int((bounds_max_lat - lat) / (bounds_max_lat - bounds_min_lat) * height)
                        # Clamp to image bounds
                        x = max(0, min(width - 1, x))
                        y = max(0, min(height - 1, y))
                        return (x, y)
                    
                    path_points = [latlon_to_pixel(p['lat'], p['lon']) for p in valid_positions]
                    
                    # Draw flight path
                    if len(path_points) > 1:
                        draw.line(path_points, fill='#3e91be', width=3)
                    
                    # Draw start marker (green circle)
                    if path_points:
                        start_x, start_y = path_points[0]
                        draw.ellipse([start_x-6, start_y-6, start_x+6, start_y+6], fill='#28a745', outline='white', width=2)
                    
                    # Draw end marker (red circle)
                    if len(path_points) > 1:
                        end_x, end_y = path_points[-1]
                        draw.ellipse([end_x-6, end_y-6, end_x+6, end_y+6], fill='#dc3545', outline='white', width=2)
                    
                    # Save to bytes
                    output = BytesIO()
                    img.save(output, format='PNG')
                    image_data = output.getvalue()
                    os.unlink(tmp_path)
                    
                    # Send image
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Cache-Control', 'public, max-age=3600')  # Cache for 1 hour
                    self.end_headers()
                    self.wfile.write(image_data)
                    return
                    
                except ImportError:
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Map generation not available',
                        'message': 'map_to_png.py dependencies not installed'
                    }).encode())
                    return
                except Exception as e:
                    print(f"   ✗ Error generating map: {e}")
                    import traceback
                    traceback.print_exc()
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Map generation error',
                        'message': str(e)
                    }).encode())
                    return
            
            # Route: /api/flights/{id}/positions
            elif len(path_parts) >= 4 and path_parts[2].isdigit() and path_parts[3] == 'positions':
                flight_id = int(path_parts[2])
                print(f"   📍 Handling positions request for flight {flight_id}")
                start_time = params.get('start_time', [None])[0]
                end_time = params.get('end_time', [None])[0]
                limit = params.get('limit', [None])[0]
                if limit:
                    limit = int(limit)
                
                print(f"   📍 Fetching positions (limit={limit})...")
                import time
                pos_start = time.time()
                positions = flight_db.get_flight_positions(flight_id, start_time, end_time, limit)
                pos_elapsed = time.time() - pos_start
                print(f"   ✓ Retrieved {len(positions)} positions in {pos_elapsed:.3f}s")
                
                # Get flight info for response
                flight = flight_db.get_flight(flight_id)
                if not flight:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Flight not found',
                        'message': f'Flight #{flight_id} does not exist'
                    }).encode())
                    return
                
                response = {
                    'flight_id': flight_id,
                    'callsign': flight.get('callsign'),
                    'aircraft_icao': flight.get('aircraft_icao'),
                    'origin': flight.get('origin'),
                    'destination': flight.get('destination'),
                    'start_time': flight.get('start_time'),
                    'end_time': flight.get('end_time'),
                    'status': flight.get('status'),
                    'positions': positions,
                    'count': len(positions)
                }
                
                response_json = json.dumps(response)
                print(f"   ✓ Returning {len(positions)} positions ({len(response_json)} bytes)")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response_json.encode())))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response_json.encode())
                self.wfile.flush()
                print(f"   ✓ Positions response sent")
                
            # Route: /api/flights/{id}
            elif len(path_parts) >= 3 and path_parts[2].isdigit():
                flight_id = int(path_parts[2])
                
                flight = flight_db.get_flight(flight_id)
                if not flight:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Flight not found',
                        'message': f'Flight #{flight_id} does not exist'
                    }).encode())
                    return
                
                # Get position count (efficient)
                position_count = flight_db.get_flight_position_count(flight_id)
                
                # Format flight response
                response = {
                    'id': flight.get('id'),
                    'callsign': flight.get('callsign'),
                    'aircraft_icao': flight.get('aircraft_icao'),
                    'aircraft': {
                        'icao': flight.get('aircraft_icao'),
                        'registration': flight.get('registration'),
                        'type': flight.get('type'),
                        'model': flight.get('model'),
                        'manufacturer': flight.get('manufacturer')
                    },
                    'origin': flight.get('origin'),
                    'destination': flight.get('destination'),
                    'origin_country': flight.get('origin_country'),
                    'destination_country': flight.get('destination_country'),
                    'airline_code': flight.get('airline_code'),
                    'airline_name': flight.get('airline_name'),
                    'start_time': flight.get('start_time'),
                    'end_time': flight.get('end_time'),
                    'status': flight.get('status'),
                    'position_count': position_count
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                
            # Route: /api/flights (list flights)
            else:
                print(f"   ✓✓✓ Handling list flights route (no ID in path)")
                start_time = params.get('start_time', [None])[0]
                end_time = params.get('end_time', [None])[0]
                callsign = params.get('callsign', [None])[0]
                icao = params.get('icao', [None])[0]
                active_only = params.get('active_only', ['false'])[0].lower() == 'true'
                limit = params.get('limit', [None])[0]
                if limit:
                    try:
                        limit = int(limit)
                    except ValueError:
                        limit = None  # Invalid limit, don't apply any limit
                else:
                    limit = None  # No limit specified, return all matching flights
                
                print(f"   Query params: limit={limit}, active_only={active_only}")
                print(f"   Calling flight_db.get_flights()...")
                
                import time
                db_start = time.time()
                try:
                    flights = flight_db.get_flights(
                        start_time=start_time,
                        end_time=end_time,
                        callsign=callsign,
                        icao=icao,
                        active_only=active_only,
                        limit=limit
                    )
                    db_elapsed = time.time() - db_start
                    print(f"   ✓ flight_db.get_flights() returned {len(flights)} flights in {db_elapsed:.3f}s")
                except Exception as e:
                    db_elapsed = time.time() - db_start
                    print(f"   ✗ Error in flight_db.get_flights() after {db_elapsed:.3f}s: {e}")
                    import traceback
                    traceback.print_exc()
                    # Send error response instead of raising
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': str(e)}).encode())
                    return
                
                print(f"   Formatting {len(flights)} flights for response...")
                
                # Skip position counts for now - they're slow and not critical for the list view
                # Users can see position counts when they expand a flight
                position_counts = {}
                
                # Format flights for response
                flight_list = []
                for idx, flight in enumerate(flights):
                    if idx == 0:
                        print(f"   First flight: id={flight.get('id')}, callsign={flight.get('callsign')}")
                    # Set position count to None - will be fetched on demand when user expands
                    position_count = None
                    
                    # Get airline logo URL if airline_code is available
                    airline_logo = None
                    airline_code = flight.get('airline_code')
                    if airline_code:
                        try:
                            from airline_logos import get_logo_url
                            airline_logo = get_logo_url(airline_code)
                        except Exception as e:
                            print(f"   Warning: Could not get airline logo for {airline_code}: {e}")
                    
                    flight_data = {
                        'id': flight.get('id'),
                        'callsign': flight.get('callsign'),
                        'aircraft_icao': flight.get('aircraft_icao'),
                        'aircraft': {
                            'icao': flight.get('aircraft_icao'),
                            'registration': flight.get('registration'),
                            'type': flight.get('type'),
                            'model': flight.get('model'),
                            'manufacturer': flight.get('manufacturer')
                        },
                        'origin': flight.get('origin'),
                        'destination': flight.get('destination'),
                        'origin_country': flight.get('origin_country'),
                        'destination_country': flight.get('destination_country'),
                        'airline_code': airline_code,
                        'airline_name': flight.get('airline_name'),
                        'airline_logo': airline_logo,
                        'start_time': flight.get('start_time'),
                        'end_time': flight.get('end_time'),
                        'status': flight.get('status'),
                        'position_count': position_count
                    }
                    flight_list.append(flight_data)
                
                response = {
                    'flights': flight_list,
                    'count': len(flight_list)
                }
                
                response_json = json.dumps(response)
                print(f"   ✓ Returning {len(flight_list)} flights (response size: {len(response_json)} bytes)")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')  # Add CORS header
                self.send_header('Content-Length', str(len(response_json.encode())))
                self.end_headers()
                self.wfile.write(response_json.encode())
                self.wfile.flush()  # Ensure response is sent immediately
                print(f"   ✓ Response sent successfully ({len(response_json)} bytes)")
                
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Flights API error: {error_msg}")
            print(traceback.format_exc())
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': error_msg}).encode())
    
    def handle_aircraft_api(self):
        """Handle aircraft API requests"""
        from urllib.parse import urlparse, parse_qs
        
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            
            # Parse path: /api/aircraft/{icao} or /api/aircraft
            path_parts = parsed.path.strip('/').split('/')
            
            # Get database instance
            global flight_db
            if not flight_db:
                config = load_config()
                db_config = config.get('database', {})
                if db_config.get('enabled', False):
                    db_path = db_config.get('db_path', 'flights.db')
                    if not os.path.exists(db_path):
                        self.send_response(503)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Database not enabled',
                            'message': f'Database file "{db_path}" does not exist.'
                        }).encode())
                        return
                    flight_db = FlightDatabase(db_path)
                else:
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': 'Database not enabled',
                        'message': 'Database is disabled in config.json'
                    }).encode())
                    return
            
            # Route: /api/aircraft/{icao}/flights or /api/aircraft/{icao}
            if len(path_parts) >= 3:
                icao = path_parts[2]
                
                # Check if requesting flights
                if len(path_parts) >= 4 and path_parts[3] == 'flights':
                    limit = params.get('limit', [None])[0]
                    if limit:
                        limit = int(limit)
                    
                    flights = flight_db.get_aircraft_flights(icao, limit=limit)
                    
                    # Format flights
                    flight_list = []
                    for flight in flights:
                        flight_data = {
                            'id': flight.get('id'),
                            'callsign': flight.get('callsign'),
                            'origin': flight.get('origin'),
                            'destination': flight.get('destination'),
                            'start_time': flight.get('start_time'),
                            'end_time': flight.get('end_time'),
                            'status': flight.get('status')
                        }
                        flight_list.append(flight_data)
                    
                    aircraft = flight_db.get_aircraft(icao)
                    if not aircraft:
                        self.send_response(404)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Aircraft not found',
                            'message': f'Aircraft {icao} does not exist'
                        }).encode())
                        return
                    
                    response = {
                        'aircraft': {
                            'icao': aircraft.get('icao'),
                            'registration': aircraft.get('registration'),
                            'type': aircraft.get('type'),
                            'model': aircraft.get('model'),
                            'manufacturer': aircraft.get('manufacturer'),
                            'first_seen_at': aircraft.get('first_seen_at'),
                            'last_seen_at': aircraft.get('last_seen_at')
                        },
                        'flights': flight_list,
                        'count': len(flight_list)
                    }
                    
                else:
                    # Just get aircraft info
                    aircraft = flight_db.get_aircraft(icao)
                    if not aircraft:
                        self.send_response(404)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            'error': 'Aircraft not found',
                            'message': f'Aircraft {icao} does not exist'
                        }).encode())
                        return
                    
                    # Try to fetch photos and additional details (non-blocking, fast timeout)
                    # Photos are fetched asynchronously in the frontend, so we skip here to avoid blocking
                    # If you want to include photos server-side, uncomment below but be aware it will slow responses
                    photos_data = None
                    # registration = aircraft.get('registration')
                    # if registration:
                    #     try:
                    #         photos_data = get_aircraft_photos_jetapi(registration)
                    #     except Exception as e:
                    #         print(f"   ⚠️  Error fetching photos for {registration}: {e}")
                    #         photos_data = None
                    
                    response = {
                        'icao': aircraft.get('icao'),
                        'registration': aircraft.get('registration'),
                        'type': aircraft.get('type'),
                        'model': aircraft.get('model'),
                        'manufacturer': aircraft.get('manufacturer'),
                        'first_seen_at': aircraft.get('first_seen_at'),
                        'last_seen_at': aircraft.get('last_seen_at')
                    }
                    
                    # Add photos and additional details if available
                    if photos_data:
                        response['photos'] = photos_data.get('photos', [])
                        response['airline'] = photos_data.get('airline')
                        response['year'] = photos_data.get('year')
                        response['country'] = photos_data.get('country')
                        response['description'] = photos_data.get('description')
                        # Update model/manufacturer if JetAPI has better data
                        if photos_data.get('model') and not response.get('model'):
                            response['model'] = photos_data.get('model')
                        if photos_data.get('manufacturer') and not response.get('manufacturer'):
                            response['manufacturer'] = photos_data.get('manufacturer')
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                
            # Route: /api/aircraft (list aircraft)
            else:
                limit = params.get('limit', [None])[0]
                if limit:
                    limit = int(limit)
                
                aircraft_list = flight_db.list_aircraft(limit=limit)
                
                # Format aircraft for response
                response = {
                    'aircraft': aircraft_list,
                    'count': len(aircraft_list)
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Aircraft API error: {error_msg}")
            print(traceback.format_exc())
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': error_msg}).encode())

    def handle_sse(self):
        global latest_flight_data

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        client_wrapper, client_count = register_sse_client(self.wfile)
        self.close_connection = False
        print(f"SSE client connected. Total clients: {client_count}")

        try:
            if latest_flight_data:
                try:
                    client_wrapper.send_message(latest_flight_data)
                except Exception:
                    return

            while True:
                time.sleep(SSE_KEEPALIVE_INTERVAL)
                try:
                    client_wrapper.send_comment('keep-alive')
                except Exception:
                    break
        finally:
            remaining = unregister_sse_client(client_wrapper)
            print(f"SSE client disconnected. Total clients: {remaining}")
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP logs for cleaner output
        pass


class ThreadingFlightHTTPServer(ThreadingMixIn, TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_http_server(host, port):
    """Run HTTP server in a separate thread"""
    with ThreadingFlightHTTPServer((host, port), FlightHTTPHandler) as httpd:
        print(f"HTTP server running on http://{host}:{port}")
        print(f"Open http://{host}:{port}/index-maps.html in your browser")
        httpd.serve_forever()

async def flight_data_loop(config):
    """Main loop for collecting and broadcasting flight data"""
    global latest_flight_data, flight_db
    
    dump1090_url = config['dump1090_url']
    consecutive_errors = 0
    max_errors = 3
    
    # Initialize database if enabled
    db_config = config.get('database', {})
    if db_config.get('enabled', False):
        db_path = db_config.get('db_path', 'flights.db')
        flight_db = FlightDatabase(db_path)
        snapshot_interval = db_config.get('snapshot_interval_seconds', 5)
        cleanup_days = db_config.get('cleanup_days', 7)
        last_snapshot_time = time.time()
        print(f"💾 Database enabled: {db_path}")
        print(f"   Snapshot interval: {snapshot_interval} seconds")
        print(f"   Cleanup: Automatic cleanup every hour, keeping last {cleanup_days} days")
        
        # Run initial cleanup on startup
        try:
            stats_before = flight_db.get_database_stats()
            print(f"   Current database: {stats_before['snapshot_count']} snapshots, {stats_before['database_size_mb']} MB")
            snapshots_deleted, events_deleted = flight_db.cleanup_old_data(cleanup_days)
            if snapshots_deleted > 0 or events_deleted > 0:
                stats_after = flight_db.get_database_stats()
                print(f"   After startup cleanup: {stats_after['snapshot_count']} snapshots, {stats_after['database_size_mb']} MB")
        except Exception as e:
            print(f"⚠️  Initial cleanup error: {e}")
    else:
        flight_db = None
        snapshot_interval = None
        last_snapshot_time = None
    
    print("Starting flight data collection...")
    print(f"Fetching from: {dump1090_url}")
    print()
    
    while True:
        data = get_aircraft(dump1090_url)
        if data:
            consecutive_errors = 0  # Reset error counter on success
            # Process and enrich flight data
            flight_update = process_aircraft_data(data)
            latest_flight_data = flight_update
            
            # Debug: Log position updates for first few flights
            flights_with_position = [f for f in flight_update.get('flights', []) if f.get('lat') and f.get('lon')]
            if flights_with_position:
                debug_flight = flights_with_position[0]
                callsign = debug_flight.get('callsign', debug_flight.get('icao', 'Unknown'))
                print(f"📡 Update: {callsign} at {debug_flight.get('lat', 0):.5f}, {debug_flight.get('lon', 0):.5f} (alt: {debug_flight.get('altitude', 'N/A')}, speed: {debug_flight.get('speed', 'N/A')})")
            
            # Save snapshot to database if enabled
            if flight_db and snapshot_interval:
                current_time = time.time()
                if current_time - last_snapshot_time >= snapshot_interval:
                    try:
                        flights = flight_update.get('flights', [])
                        if flights:
                            flight_db.save_snapshot(flights)
                            last_snapshot_time = current_time
                    except Exception as e:
                        print(f"⚠️  Database error: {e}")
            
            broadcast_sse(flight_update)
        else:
            consecutive_errors += 1
            if consecutive_errors == max_errors:
                print(f"⚠️  Warning: Cannot connect to dump1090 at {dump1090_url}")
                print("   Check if dump1090 is running and the IP address is correct.")
                print("   (This message will only appear once)")
                consecutive_errors = max_errors + 1  # Prevent repeated messages
        
        # Print API call summary every 60 seconds
        if not hasattr(flight_data_loop, '_last_summary_time'):
            flight_data_loop._last_summary_time = time.time()
        
        # Database cleanup check (every hour)
        if not hasattr(flight_data_loop, '_last_cleanup_time'):
            flight_data_loop._last_cleanup_time = time.time()
        
        current_time = time.time()
        if current_time - flight_data_loop._last_summary_time >= 60:  # Every 60 seconds
            flight_data_loop._last_summary_time = current_time
            with api_tracker_lock:
                if api_call_tracker:
                    print("\n" + "=" * 80)
                    print("📊 API CALL SUMMARY (last 60 seconds):")
                    print("=" * 80)
                    total_route_calls = sum(tracker['route_calls'] for tracker in api_call_tracker.values())
                    total_aircraft_calls = sum(tracker['aircraft_calls'] for tracker in api_call_tracker.values())
                    print(f"Total route API calls: {total_route_calls}")
                    print(f"Total aircraft info API calls: {total_aircraft_calls}")
                    print(f"Total unique flights tracked: {len(api_call_tracker)}")
                    print("\nPer-flight breakdown:")
                    for icao, tracker in sorted(api_call_tracker.items(), key=lambda x: x[1]['route_calls'] + x[1]['aircraft_calls'], reverse=True)[:10]:
                        callsign = flight_memory.get(icao, {}).get('callsign', 'Unknown')
                        print(f"  {callsign} ({icao}): {tracker['route_calls']} route calls, {tracker['aircraft_calls']} aircraft calls (first: {tracker['first_call']}, last: {tracker['last_call']})")
                    print("=" * 80 + "\n")
            
            # Database stats
            if flight_db:
                try:
                    stats = flight_db.get_database_stats()
                    print(f"💾 Database: {stats['snapshot_count']} snapshots, {stats['unique_flights']} flights, {stats['database_size_mb']} MB")
                except Exception as e:
                    pass
        
        # Database cleanup (every hour)
        if flight_db and current_time - flight_data_loop._last_cleanup_time >= 3600:  # Every hour
            flight_data_loop._last_cleanup_time = current_time
            try:
                db_config = config.get('database', {})
                cleanup_days = db_config.get('cleanup_days', 7)
                
                # Get stats before cleanup
                stats_before = flight_db.get_database_stats()
                
                # Run cleanup
                snapshots_deleted, events_deleted = flight_db.cleanup_old_data(cleanup_days)
                
                # Get stats after cleanup
                stats_after = flight_db.get_database_stats()
                
                if snapshots_deleted > 0 or events_deleted > 0:
                    print(f"🧹 Database cleanup complete:")
                    print(f"   Before: {stats_before['snapshot_count']} snapshots, {stats_before['database_size_mb']} MB")
                    print(f"   After: {stats_after['snapshot_count']} snapshots, {stats_after['database_size_mb']} MB")
                    print(f"   Deleted: {snapshots_deleted} snapshots, {events_deleted} events (older than {cleanup_days} days)")
                else:
                    print(f"🧹 Database cleanup: No data older than {cleanup_days} days to delete")
            except Exception as e:
                print(f"⚠️  Database cleanup error: {e}")
                import traceback
                traceback.print_exc()
        
        await asyncio.sleep(1)  # Update every 1 second

async def main():
    """Main async function"""
    config = load_config()
    
    http_host = config.get('http_host', '0.0.0.0')
    http_port = config.get('http_port', 8080)
    
    print("=" * 70)
    print("Flight Tracker Server (with Maps)")
    print("=" * 70)
    print()
    
    # Check and report Inky display status
    if HAS_INKY_DISPLAY:
        print("✓ Inky display: Available (maps will be displayed automatically)")
    else:
        print("⚠️  Inky display: Not available (maps will be generated but not displayed)")
    print()
    
    # Start HTTP server in background thread
    http_thread = threading.Thread(
        target=run_http_server,
        args=(http_host, http_port),
        daemon=True
    )
    http_thread.start()
    
    # Give HTTP server time to start
    await asyncio.sleep(0.5)
    
    print(f"SSE endpoint available at http://{http_host}:{http_port}/events")

    # Run flight data loop
    await flight_data_loop(config)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopping server...")
        sys.exit(0)

