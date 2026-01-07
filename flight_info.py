#!/usr/bin/env python3
"""
Flight information lookup utility
Uses adsb.lol API to get origin and destination
Uses OpenFlights database to get airport country information
"""

import requests
import sys
import os
import time
from datetime import datetime

# OpenFlights airport database URL and cache file
OPENFLIGHTS_AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
OPENFLIGHTS_AIRPORTS_CACHE = "airports_cache.dat"

# No static airport mapping - we use OpenFlights database for airport info

def load_openflights_airports():
    """
    Load airport data from OpenFlights (downloads and caches if needed)
    
    Returns:
        dict: {iata_code: {'country': '...', 'name': '...', 'city': '...'}, 
               icao_code: {...}}
    """
    airports = {}
    
    # Check if cache exists and is recent (less than 7 days old)
    if os.path.exists(OPENFLIGHTS_AIRPORTS_CACHE):
        cache_age = time.time() - os.path.getmtime(OPENFLIGHTS_AIRPORTS_CACHE)
        if cache_age < 7 * 24 * 3600:  # 7 days
            try:
                with open(OPENFLIGHTS_AIRPORTS_CACHE, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        # Parse CSV - handle quoted fields
                        parts = []
                        current = ''
                        in_quotes = False
                        for char in line:
                            if char == '"':
                                in_quotes = not in_quotes
                            elif char == ',' and not in_quotes:
                                parts.append(current.strip())
                                current = ''
                            else:
                                current += char
                        if current:
                            parts.append(current.strip())
                        
                        if len(parts) >= 6:
                            name = parts[1].strip('"').strip()
                            city = parts[2].strip('"').strip()
                            country = parts[3].strip('"').strip()
                            iata = parts[4].strip('"').strip() if len(parts) > 4 else ''
                            icao = parts[5].strip('"').strip() if len(parts) > 5 else ''
                            
                            # Parse latitude and longitude (columns 6 and 7)
                            lat = None
                            lon = None
                            try:
                                if len(parts) > 6:
                                    lat_str = parts[6].strip('"').strip()
                                    if lat_str and lat_str != '\\N':
                                        lat = float(lat_str)
                                if len(parts) > 7:
                                    lon_str = parts[7].strip('"').strip()
                                    if lon_str and lon_str != '\\N':
                                        lon = float(lon_str)
                            except (ValueError, IndexError):
                                pass
                            
                            airport_info = {
                                'country': country,
                                'name': name,
                                'city': city,
                                'lat': lat,
                                'lon': lon
                            }
                            
                            if iata and iata != '\\N' and iata != '':
                                airports[iata.upper()] = airport_info
                            if icao and icao != '\\N' and icao != '':
                                airports[icao.upper()] = airport_info
                return airports
            except Exception as e:
                print(f"Warning: Could not load cached airport data: {e}")
    
    # Download fresh data from OpenFlights
    try:
        print("Downloading airport data from OpenFlights...")
        response = requests.get(OPENFLIGHTS_AIRPORTS_URL, timeout=15)
        response.raise_for_status()
        
        # Save to cache
        with open(OPENFLIGHTS_AIRPORTS_CACHE, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        # Parse the data
        lines = response.text.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
            # Parse CSV - handle quoted fields
            parts = []
            current = ''
            in_quotes = False
            for char in line:
                if char == '"':
                    in_quotes = not in_quotes
                elif char == ',' and not in_quotes:
                    parts.append(current.strip())
                    current = ''
                else:
                    current += char
            if current:
                parts.append(current.strip())
            
            if len(parts) >= 6:
                name = parts[1].strip('"').strip()
                city = parts[2].strip('"').strip()
                country = parts[3].strip('"').strip()
                iata = parts[4].strip('"').strip() if len(parts) > 4 else ''
                icao = parts[5].strip('"').strip() if len(parts) > 5 else ''
                
                # Parse latitude and longitude (columns 6 and 7)
                lat = None
                lon = None
                try:
                    if len(parts) > 6:
                        lat_str = parts[6].strip('"').strip()
                        if lat_str and lat_str != '\\N':
                            lat = float(lat_str)
                    if len(parts) > 7:
                        lon_str = parts[7].strip('"').strip()
                        if lon_str and lon_str != '\\N':
                            lon = float(lon_str)
                except (ValueError, IndexError):
                    pass
                
                airport_info = {
                    'country': country,
                    'name': name,
                    'city': city,
                    'lat': lat,
                    'lon': lon
                }
                
                if iata and iata != '\\N' and iata != '':
                    airports[iata.upper()] = airport_info
                if icao and icao != '\\N' and icao != '':
                    airports[icao.upper()] = airport_info
        
        print(f"Loaded {len(airports)} airports from OpenFlights")
        return airports
    except Exception as e:
        print(f"Warning: Could not download airport data from OpenFlights: {e}")
        return {}

def get_airport_country(airport_code):
    """
    Get country name for an airport code from OpenFlights database
    
    Args:
        airport_code: IATA or ICAO airport code (e.g., 'WNZ', 'ZSWZ')
    
    Returns:
        str: Country name or None if not found
    """
    if not airport_code:
        return None
    
    airport_code = airport_code.upper()
    
    try:
        airports = load_openflights_airports()
        airport_info = airports.get(airport_code)
        if airport_info:
            return airport_info.get('country')
    except:
        pass
    
    return None

def get_airport_coordinates(airport_code):
    """
    Get latitude and longitude for an airport code from OpenFlights database
    
    Args:
        airport_code: IATA or ICAO airport code (e.g., 'BER', 'EDDB')
    
    Returns:
        tuple: (lat, lon) or (None, None) if not found
    """
    if not airport_code:
        return (None, None)
    
    airport_code = airport_code.upper()
    
    try:
        airports = load_openflights_airports()
        airport_info = airports.get(airport_code)
        if airport_info:
            lat = airport_info.get('lat')
            lon = airport_info.get('lon')
            return (lat, lon)
    except:
        pass
    
    return (None, None)

def get_city_name_from_coordinates(lat, lon):
    """
    Get city name from coordinates using OpenStreetMap Nominatim API
    
    Args:
        lat: Latitude
        lon: Longitude
    
    Returns:
        str: City name or None if not found
    """
    if lat is None or lon is None:
        return None
    
    try:
        # Use Nominatim reverse geocoding (free, no API key required)
        url = f"https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 10  # City level
        }
        headers = {
            'User-Agent': 'FlightTracker/1.0'  # Required by Nominatim
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            
            # Try various city name fields
            city = (address.get('city') or 
                   address.get('town') or 
                   address.get('village') or
                   address.get('municipality') or
                   address.get('county'))
            
            return city
    except Exception as e:
        pass
    
    return None

def get_current_position_adsblol(icao):
    """Get current aircraft position from adsb.lol by ICAO"""
    url = f"https://api.adsb.lol/v2/hex/{icao}"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        print(f"[{timestamp}] API CALL: get_current_position_adsblol - ICAO: {icao}")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            ac_list = data.get('ac', [])
            if ac_list and len(ac_list) > 0:
                ac = ac_list[0]
                lat = ac.get('lat')
                lon = ac.get('lon')
                if lat and lon:
                    print(f"[{timestamp}] API SUCCESS: Position found for {icao}: {lat}, {lon}")
                    return {'lat': lat, 'lon': lon}
            print(f"[{timestamp}] API WARNING: No position data for {icao}")
        else:
            print(f"[{timestamp}] API ERROR: Status {response.status_code} for {icao}")
    except Exception as e:
        print(f"[{timestamp}] API EXCEPTION: {icao} - {str(e)}")
    return None

def get_aircraft_photos_jetapi(registration):
    """
    Get aircraft photos from Wikimedia Commons (free, no API key required)
    
    Args:
        registration: Aircraft registration/tail number (e.g., 'D-AIUL', 'N12345')
    
    Returns:
        dict with aircraft photos and details or None
    """
    if not registration:
        return None
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        print(f"[{timestamp}] API CALL: get_aircraft_photos - Registration: {registration}")
        
        # Search Wikimedia Commons for images of this aircraft
        search_url = "https://commons.wikimedia.org/w/api.php"
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'search',
            'srsearch': registration,
            'srnamespace': 6,  # File namespace
            'srlimit': 5,
            'srprop': 'size|timestamp'
        }
        
        headers = {
            'User-Agent': 'FlightTracker/1.0 (https://github.com/your-repo)'
        }
        response = requests.get(search_url, params=params, headers=headers, timeout=3)
        if response.status_code != 200:
            print(f"[{timestamp}] API ERROR: Wikimedia API returned status {response.status_code}")
            return None
        
        data = response.json()
        search_results = data.get('query', {}).get('search', [])
        
        if not search_results:
            print(f"[{timestamp}] API INFO: No photos found for {registration} in Wikimedia Commons")
            return None
        
        # Get image URLs for the found files
        file_titles = [result['title'] for result in search_results]
        image_params = {
            'action': 'query',
            'format': 'json',
            'titles': '|'.join(file_titles),
            'prop': 'imageinfo',
            'iiprop': 'url|thumburl|extmetadata',
            'iiurlwidth': 400  # Thumbnail width
        }
        
        image_response = requests.get(search_url, params=image_params, headers=headers, timeout=3)
        if image_response.status_code != 200:
            print(f"[{timestamp}] API ERROR: Failed to get image URLs")
            return None
        
        image_data = image_response.json()
        pages = image_data.get('query', {}).get('pages', {})
        
        photos = []
        for page_id, page_info in pages.items():
            if page_id == '-1':  # Missing page
                continue
            
            imageinfo = page_info.get('imageinfo', [])
            if imageinfo:
                img_info = imageinfo[0]
                photo_url = img_info.get('url') or img_info.get('thumburl')
                if photo_url:
                    # Extract metadata if available
                    extmetadata = img_info.get('extmetadata', {})
                    photographer = None
                    if 'Artist' in extmetadata:
                        photographer_raw = extmetadata['Artist'].get('value', '')
                        # Strip HTML tags from photographer name
                        import re
                        photographer = re.sub(r'<[^>]+>', '', photographer_raw).strip()
                    elif 'Photographer' in extmetadata:
                        photographer_raw = extmetadata['Photographer'].get('value', '')
                        import re
                        photographer = re.sub(r'<[^>]+>', '', photographer_raw).strip()
                    
                    date_value = None
                    if extmetadata:
                        if 'DateTimeOriginal' in extmetadata:
                            date_value = extmetadata['DateTimeOriginal'].get('value', '')
                        elif 'DateTime' in extmetadata:
                            date_value = extmetadata['DateTime'].get('value', '')
                    
                    photos.append({
                        'url': photo_url,
                        'thumbnail': img_info.get('thumburl') or photo_url,
                        'photographer': photographer,
                        'date': date_value
                    })
        
        if photos:
            result = {
                'photos': photos[:3],  # Limit to 3 photos
                'registration': registration
            }
            print(f"[{timestamp}] API SUCCESS: Found {len(photos)} photos for {registration} in Wikimedia Commons")
            return result
        else:
            print(f"[{timestamp}] API INFO: No valid photo URLs found for {registration}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"[{timestamp}] API ERROR: Request timeout for {registration}")
        return None
    except Exception as e:
        print(f"[{timestamp}] API ERROR: Exception for {registration}: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_aircraft_info_adsblol(icao):
    """
    Get aircraft information (model, type, registration) from adsb.lol by ICAO
    
    Args:
        icao: ICAO24 hex code (e.g., '3c55c7')
    
    Returns:
        dict with aircraft info: {'model': '...', 'type': '...', 'registration': '...'} or None
    """
    url = f"https://api.adsb.lol/v2/hex/{icao}"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        print(f"[{timestamp}] API CALL: get_aircraft_info_adsblol - ICAO: {icao}")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            ac_list = data.get('ac', [])
            if ac_list and len(ac_list) > 0:
                ac = ac_list[0]
                result = {}
                
                # Try to get aircraft type/model information
                # adsb.lol might have 'type', 't', 'desc', or similar fields
                if 'type' in ac:
                    result['type'] = ac.get('type')
                if 't' in ac:
                    result['type'] = ac.get('t')
                if 'desc' in ac:
                    result['model'] = ac.get('desc')
                if 'r' in ac:
                    result['registration'] = ac.get('r')
                if 'registration' in ac:
                    result['registration'] = ac.get('registration')
                
                # Also check for aircraft database info
                db = data.get('db', {})
                if db:
                    if 't' in db:
                        result['type'] = db.get('t')
                    if 'desc' in db:
                        result['model'] = db.get('desc')
                    if 'r' in db:
                        result['registration'] = db.get('r')
                    if 'manufacturer' in db:
                        result['manufacturer'] = db.get('manufacturer')
                
                if result:
                    print(f"[{timestamp}] API SUCCESS: Aircraft info found for {icao}: {result}")
                    return result
                else:
                    print(f"[{timestamp}] API WARNING: No aircraft info for {icao}")
            else:
                print(f"[{timestamp}] API WARNING: No aircraft data in response for {icao}")
        else:
            print(f"[{timestamp}] API ERROR: Status {response.status_code} for {icao}")
    except Exception as e:
        print(f"[{timestamp}] API EXCEPTION: {icao} - {str(e)}")
    return None

def get_flight_route_adsblol(callsign, icao=None, lat=None, lon=None):
    """Get flight route from adsb.lol routeset API
    
    Args:
        callsign: Flight callsign (required)
        icao: ICAO24 hex code (optional, used to get position if lat/lon not provided)
        lat: Latitude (optional, will be fetched if not provided)
        lon: Longitude (optional, will be fetched if not provided)
    
    Returns:
        dict with 'origin', 'destination', 'source' keys, or None if not found
    """
    if not callsign:
        return None
    
    # Get position if not provided
    if (lat is None or lon is None) and icao:
        pos = get_current_position_adsblol(icao)
        if pos:
            lat = pos.get('lat')
            lon = pos.get('lon')
    
    # We need lat/lon for the API
    if lat is None or lon is None:
        return None
    
    url = "https://api.adsb.lol/api/0/routeset"
    payload = {
        "planes": [{
            "callsign": callsign.strip(),
            "lat": lat,
            "lng": lon
        }]
    }
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        print(f"[{timestamp}] API CALL: get_flight_route_adsblol - Callsign: {callsign.strip()}, ICAO: {icao}, Position: {lat}, {lon}")
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            routes = response.json()
            if routes and len(routes) > 0:
                route = routes[0]
                airport_codes = route.get('airport_codes', '')
                airports = route.get('_airports', [])
                
                if airports and len(airports) >= 2:
                    # Prefer IATA codes (more user-friendly) but fallback to ICAO
                    origin_iata = airports[0].get('iata')
                    origin_icao = airports[0].get('icao')
                    destination_iata = airports[1].get('iata')
                    destination_icao = airports[1].get('icao')
                    
                    origin = origin_iata or origin_icao
                    destination = destination_iata or destination_icao
                    
                    # Try to get country from adsb.lol API response first
                    origin_country = airports[0].get('country') or airports[0].get('country_code')
                    destination_country = airports[1].get('country') or airports[1].get('country_code')
                    
                    # Fallback to OpenFlights database if adsb.lol doesn't provide country
                    # Try IATA first, then ICAO if IATA lookup fails
                    if not origin_country:
                        if origin_iata:
                            origin_country = get_airport_country(origin_iata)
                        if not origin_country and origin_icao:
                            origin_country = get_airport_country(origin_icao)
                    
                    if not destination_country:
                        if destination_iata:
                            destination_country = get_airport_country(destination_iata)
                        if not destination_country and destination_icao:
                            destination_country = get_airport_country(destination_icao)
                    
                    if origin and destination:
                        result = {
                            'origin': origin,
                            'destination': destination,
                            'source': 'adsb.lol'
                        }
                        # Include country if available (from API or OpenFlights)
                        if origin_country:
                            result['origin_country'] = origin_country
                        if destination_country:
                            result['destination_country'] = destination_country
                        print(f"[{timestamp}] API SUCCESS: Route found for {callsign.strip()}: {origin} → {destination}")
                        return result
            print(f"[{timestamp}] API WARNING: No route found for {callsign.strip()}")
        else:
            print(f"[{timestamp}] API ERROR: Status {response.status_code} for {callsign.strip()}")
    except Exception as e:
        print(f"[{timestamp}] API EXCEPTION: {callsign.strip()} - {str(e)}")
        # Return error info for debugging
        return {
            'origin': None,
            'destination': None,
            'source': 'adsb.lol',
            'error': str(e)
        }
    
    return None

def get_flight_route(icao, callsign=None, lat=None, lon=None):
    """
    Get flight origin and destination from adsb.lol routeset API
    
    Uses only adsb.lol (free, no rate limits, requires callsign + position)
    
    Args:
        icao: ICAO24 hex code (required, used to get position if not provided)
        callsign: Flight callsign (required)
        lat: Latitude (optional, will be fetched from adsb.lol if not provided)
        lon: Longitude (optional, will be fetched from adsb.lol if not provided)
    
    Returns:
        dict with 'origin', 'destination', 'source' keys, or None if not found
    """
    # Only use adsb.lol - requires callsign
    if not callsign:
        return None
    
    return get_flight_route_adsblol(callsign, icao, lat, lon)

if __name__ == '__main__':
    # Allow manual lookup from command line
    if len(sys.argv) < 3:
        print("Usage: python3 flight_info.py <ICAO> <CALLSIGN> [LAT] [LON]")
        print()
        print("Examples:")
        print("  python3 flight_info.py 3c55c7 EWG1AN")
        print("  python3 flight_info.py 3c55c7 EWG1AN 52.4 13.5")
        print()
        sys.exit(1)
    
    icao = sys.argv[1]
    callsign = sys.argv[2]
    
    # Parse optional lat/lon
    lat = None
    lon = None
    if len(sys.argv) > 3:
        try:
            lat = float(sys.argv[3])
        except ValueError:
            print(f"Warning: Invalid latitude '{sys.argv[3]}', ignoring")
    if len(sys.argv) > 4:
        try:
            lon = float(sys.argv[4])
        except ValueError:
            print(f"Warning: Invalid longitude '{sys.argv[4]}', ignoring")
    
    print(f"Looking up flight: {callsign} (ICAO: {icao})")
    if lat and lon:
        print(f"Using position: {lat}, {lon}")
    print()
    
    result = get_flight_route(icao, callsign, lat, lon)
    
    if result:
        if result.get('error'):
            print(f"❌ Error: {result.get('error')}")
        else:
            print("✅ Flight info found:")
            print(f"  Origin: {result.get('origin', 'Unknown')}")
            print(f"  Destination: {result.get('destination', 'Unknown')}")
            print(f"  Source: {result.get('source', 'Unknown')}")
    else:
        print("❌ Flight info not found")
        print("   (This could mean the flight is not in adsb.lol database,")
        print("    or position data is needed but unavailable)")
