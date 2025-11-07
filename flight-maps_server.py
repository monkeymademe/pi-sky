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
from socketserver import TCPServer
from math import radians, sin, cos, sqrt, atan2

# Suppress urllib3 warning
os.environ['PYTHONWARNINGS'] = 'ignore:urllib3'
warnings.filterwarnings('ignore', message='.*urllib3.*')

import requests
import websockets

from flight_info import get_flight_route, get_aircraft_info_adsblol
from airline_logos import get_airline_info

# Global state
flight_memory = {}
latest_flight_data = None
websocket_clients = set()

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
    except requests.exceptions.Timeout:
        # Connection timeout - dump1090 might be down or unreachable
        return None
    except requests.exceptions.ConnectionError as e:
        # Connection error - network issue or dump1090 not running
        return None
    except requests.RequestException as e:
        # Other HTTP errors
        return None

def process_aircraft_data(aircraft_data):
    """
    Process raw aircraft data: filter, enrich, and update memory
    
    Returns:
        dict: Enriched flight data ready for broadcasting
    """
    global flight_memory
    
    aircraft = aircraft_data.get('aircraft', [])
    
    # Filter out aircraft without callsigns
    aircraft_with_callsigns = [ac for ac in aircraft if ac.get('flight', '').strip()]
    
    # Filter out stale data (seen > 60 seconds ago)
    recent_aircraft = [ac for ac in aircraft_with_callsigns if ac.get('seen', 999) <= 60]
    
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
        
        # Create enriched flight data
        enriched = {
            'icao': icao,
            'callsign': callsign,
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
            'distance': distance  # Distance from receiver in km
        }
        
        # Add new flights or update existing ones
        if icao not in flight_memory:
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
                    route_info = get_flight_route(icao, callsign, lat, lon)
                    if route_info:
                        if route_info.get('error'):
                            flight_memory[icao]['lookup_error'] = route_info.get('error')
                        else:
                            flight_memory[icao]['origin'] = route_info.get('origin')
                            flight_memory[icao]['destination'] = route_info.get('destination')
                            flight_memory[icao]['origin_country'] = route_info.get('origin_country')
                            flight_memory[icao]['destination_country'] = route_info.get('destination_country')
                            flight_memory[icao]['source'] = route_info.get('source', 'unknown')
                except Exception as e:
                    flight_memory[icao]['lookup_error'] = str(e)
            
            # Lookup aircraft information (model, type, registration) from adsb.lol
            if icao != 'Unknown':
                try:
                    flight_memory[icao]['aircraft_lookup_attempted'] = True
                    aircraft_info = get_aircraft_info_adsblol(icao)
                    if aircraft_info:
                        flight_memory[icao]['aircraft_model'] = aircraft_info.get('model')
                        flight_memory[icao]['aircraft_type'] = aircraft_info.get('type')
                        flight_memory[icao]['aircraft_registration'] = aircraft_info.get('registration')
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
            
            # Retry route lookup on 5th cycle if no route info yet (requires callsign)
            if flight_memory[icao]['seen_cycles'] == 5:
                if not flight_memory[icao].get('origin') and callsign and icao != 'Unknown':
                    try:
                        flight_memory[icao]['lookup_attempted'] = True
                        lat = ac.get('lat')
                        lon = ac.get('lon')
                        route_info = get_flight_route(icao, callsign, lat, lon)
                        if route_info:
                            if route_info.get('error'):
                                flight_memory[icao]['lookup_error'] = route_info.get('error')
                            else:
                                flight_memory[icao]['origin'] = route_info.get('origin')
                                flight_memory[icao]['destination'] = route_info.get('destination')
                                flight_memory[icao]['origin_country'] = route_info.get('origin_country')
                                flight_memory[icao]['destination_country'] = route_info.get('destination_country')
                                flight_memory[icao]['source'] = route_info.get('source', 'unknown')
                    except Exception as e:
                        flight_memory[icao]['lookup_error'] = str(e)
        
        # Add memory data to enriched flight
        if icao in flight_memory:
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
            enriched['status'] = 'new'
            # Add airline logo info if available (for new flights)
            if airline_info:
                enriched['airline_code'] = airline_info.get('code')
                enriched['airline_logo'] = airline_info.get('logo_url')
                enriched['airline_name'] = airline_info.get('name')
        
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
        'with_callsigns': len(aircraft_with_callsigns),
        'total': len(aircraft),
        'timestamp': datetime.now().isoformat()
    }
    
    # Include receiver position for map
    config = load_config()
    stats['receiver_lat'] = config.get('receiver_lat')
    stats['receiver_lon'] = config.get('receiver_lon')
    stats['hide_receiver'] = config.get('hide_receiver', False)
    
    return {
        'type': 'flight_update',
        'timestamp': datetime.now().isoformat(),
        'stats': stats,
        'flights': enriched_flights,
        'flight_count': len(enriched_flights)
    }

# WebSocket handler
async def handle_websocket(websocket):
    """Handle WebSocket client connection"""
    global websocket_clients
    
    websocket_clients.add(websocket)
    print(f"WebSocket client connected. Total clients: {len(websocket_clients)}")
    
    # Send latest data immediately if available
    if latest_flight_data:
        try:
            await websocket.send(json.dumps(latest_flight_data))
        except websockets.exceptions.ConnectionClosed:
            pass
    
    try:
        # Keep connection alive - clients can send pings
        async for message in websocket:
            if message == 'ping':
                await websocket.send('pong')
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        websocket_clients.discard(websocket)
        print(f"WebSocket client disconnected. Total clients: {len(websocket_clients)}")

async def broadcast_flight_data(data):
    """Broadcast flight data to all WebSocket clients"""
    global websocket_clients
    
    if not websocket_clients:
        return
    
    message = json.dumps(data)
    disconnected = set()
    
    for client in websocket_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)
        except Exception as e:
            print(f"Error broadcasting to client: {e}")
            disconnected.add(client)
    
    # Clean up disconnected clients
    websocket_clients -= disconnected

# HTTP server
class FlightHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.path.dirname(__file__), 'web'), **kwargs)
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP logs for cleaner output
        pass

def run_http_server(host, port):
    """Run HTTP server in a separate thread"""
    with TCPServer((host, port), FlightHTTPHandler) as httpd:
        print(f"HTTP server running on http://{host}:{port}")
        print(f"Open http://{host}:{port}/index-maps.html in your browser")
        httpd.serve_forever()

async def run_websocket_server(host, port):
    """Run WebSocket server"""
    async with websockets.serve(handle_websocket, host, port):
        print(f"WebSocket server running on ws://{host}:{port}")
        await asyncio.Future()  # Run forever

async def flight_data_loop(config):
    """Main loop for collecting and broadcasting flight data"""
    global latest_flight_data
    
    dump1090_url = config['dump1090_url']
    consecutive_errors = 0
    max_errors = 3
    
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
            
            # Broadcast to WebSocket clients
            if websocket_clients:
                await broadcast_flight_data(flight_update)
        else:
            consecutive_errors += 1
            if consecutive_errors == max_errors:
                print(f"⚠️  Warning: Cannot connect to dump1090 at {dump1090_url}")
                print("   Check if dump1090 is running and the IP address is correct.")
                print("   (This message will only appear once)")
                consecutive_errors = max_errors + 1  # Prevent repeated messages
        
        await asyncio.sleep(5)  # Update every 5 seconds

async def main():
    """Main async function"""
    config = load_config()
    
    http_host = config.get('http_host', '0.0.0.0')
    http_port = config.get('http_port', 8080)
    ws_host = config.get('websocket_host', '0.0.0.0')
    ws_port = config.get('websocket_port', 8765)
    
    print("=" * 70)
    print("Flight Tracker Server (with Maps)")
    print("=" * 70)
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
    
    # Run WebSocket server and flight data loop concurrently
    await asyncio.gather(
        run_websocket_server(ws_host, ws_port),
        flight_data_loop(config)
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopping server...")
        sys.exit(0)

