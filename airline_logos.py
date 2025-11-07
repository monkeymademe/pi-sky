#!/usr/bin/env python3
"""
Airline logo utilities
Extracts airline codes from callsigns and generates logo URLs
Uses OpenFlights airline data for comprehensive airline information
"""

import re
import os
import csv
import requests
from urllib.parse import urlparse

def extract_airline_code(callsign):
    """
    Extract airline IATA/ICAO code from callsign using regex
    
    Examples:
        "DLH123" -> "DLH" (Lufthansa)
        "UAE456" -> "UAE" (Emirates)
        "BAW789" -> "BAW" (British Airways)
        "EWG1AN" -> "EWG" (Eurowings)
    
    Args:
        callsign: Flight callsign string
    
    Returns:
        str: Airline code (2-3 letters) or None
    """
    if not callsign:
        return None
    
    callsign = callsign.strip().upper()
    
    # Common pattern: 3-letter ICAO airline code followed by numbers/letters
    # Examples: DLH123, QTR91Y, BAW789
    match = re.match(r'^([A-Z]{2,3})[0-9A-Z]+', callsign)
    if match:
        airline_code = match.group(1)
        return airline_code
    
    return None

# OpenFlights airline data URL (free, updated regularly)
OPENFLIGHTS_AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
OPENFLIGHTS_CACHE_FILE = "airlines_cache.dat"

# Mapping of common airline codes to their official website domains and names
# Used to fetch favicons/logos via free services
# Note: OpenFlights data is used for airline names, but domains still need to be manually mapped
AIRLINE_DOMAINS = {
    # Major European airlines
    'DLH': ('lufthansa.com', 'Lufthansa'),
    'BAW': ('britishairways.com', 'British Airways'),
    'AFR': ('airfrance.com', 'Air France'),
    'KLM': ('klm.com', 'KLM'),
    'AZA': ('alitalia.com', 'Alitalia'),
    'IBE': ('iberia.com', 'Iberia'),
    'EZY': ('easyjet.com', 'EasyJet'),
    'RYR': ('ryanair.com', 'Ryanair'),
    'EWG': ('eurowings.com', 'Eurowings'),
    'EJU': ('easyjet.com', 'EasyJet Europe'),  # EasyJet Europe
    'WZZ': ('wizzair.com', 'Wizz Air'),
    'SAS': ('sas.se', 'Scandinavian Airlines'),
    'TAP': ('flytap.com', 'TAP Air Portugal'),
    'AAL': ('aa.com', 'American Airlines'),
    'UAL': ('united.com', 'United Airlines'),
    'DAL': ('delta.com', 'Delta Air Lines'),
    'SWA': ('southwest.com', 'Southwest Airlines'),
    'JBU': ('jetblue.com', 'JetBlue'),
    # Middle Eastern
    'UAE': ('emirates.com', 'Emirates'),
    'QTR': ('qatarairways.com', 'Qatar Airways'),
    'ETD': ('etihad.com', 'Etihad Airways'),
    'SVA': ('svairlines.com', 'Saudia'),
    # Asian
    'SIA': ('singaporeair.com', 'Singapore Airlines'),
    'CPA': ('cathaypacific.com', 'Cathay Pacific'),
    'JAL': ('jal.com', 'Japan Airlines'),
    'AAR': ('flyasiana.com', 'Asiana Airlines'),
    'THA': ('thaiairways.com', 'Thai Airways'),
    # Australian
    'QFA': ('qantas.com', 'Qantas'),
    # Additional European
    'CFG': ('condor.com', 'Condor'),
    'SXS': ('sunexpress.com', 'SunExpress'),
    'SWU': ('swiss.com', 'Swiss International Air Lines'),
    'FIN': ('finnair.com', 'Finnair'),
    'VJH': ('vueling.com', 'Vueling'),
}

def load_openflights_data():
    """
    Load airline data from OpenFlights (downloads and caches if needed)
    
    Returns:
        dict: {icao_code: airline_name, iata_code: airline_name}
    """
    airlines = {}
    
    # Check if cache exists and is recent (less than 7 days old)
    if os.path.exists(OPENFLIGHTS_CACHE_FILE):
        import time
        cache_age = time.time() - os.path.getmtime(OPENFLIGHTS_CACHE_FILE)
        if cache_age < 7 * 24 * 3600:  # 7 days
            try:
                with open(OPENFLIGHTS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip():
                            continue
                        # Parse same way as downloaded data
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
                        
                        if len(parts) >= 5:
                            name = parts[1].strip('"').strip()
                            iata = parts[3].strip('"').strip() if len(parts) > 3 else ''
                            icao = parts[4].strip('"').strip() if len(parts) > 4 else ''
                            
                            if iata and iata != '\\N' and iata != '':
                                airlines[iata.upper()] = name
                            if icao and icao != '\\N' and icao != '':
                                airlines[icao.upper()] = name
                return airlines
            except Exception as e:
                print(f"Warning: Could not load cached airline data: {e}")
    
    # Download fresh data from OpenFlights
    try:
        print("Downloading airline data from OpenFlights...")
        response = requests.get(OPENFLIGHTS_AIRLINES_URL, timeout=10)
        response.raise_for_status()
        
        # Save to cache
        with open(OPENFLIGHTS_CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        # Parse the data
        # OpenFlights format uses commas, but fields may contain commas, so we need careful parsing
        lines = response.text.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
            # OpenFlights format: id, name, alias, iata, icao, callsign, country, active
            # Fields are comma-separated, but may be quoted
            # Simple parsing: split by comma and handle quoted fields
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
            
            if len(parts) >= 5:
                name = parts[1].strip('"').strip()
                iata = parts[3].strip('"').strip() if len(parts) > 3 else ''
                icao = parts[4].strip('"').strip() if len(parts) > 4 else ''
                
                if iata and iata != '\\N' and iata != '':
                    airlines[iata.upper()] = name
                if icao and icao != '\\N' and icao != '':
                    airlines[icao.upper()] = name
        
        print(f"Loaded {len(airlines)} airlines from OpenFlights")
        return airlines
    except Exception as e:
        print(f"Warning: Could not download airline data from OpenFlights: {e}")
        # Fallback to static mapping
        return {}

def get_airline_name(airline_code):
    """
    Get airline name from airline code
    Uses OpenFlights data first, then falls back to static mapping
    
    Args:
        airline_code: IATA/ICAO airline code (2-3 letters)
    
    Returns:
        str: Airline name or None if not available
    """
    if not airline_code:
        return None
    
    airline_code = airline_code.upper()
    
    # Try OpenFlights data first (more comprehensive)
    try:
        openflights_data = load_openflights_data()
        if airline_code in openflights_data:
            return openflights_data[airline_code]
    except:
        pass
    
    # Fallback to static mapping (includes domain info)
    airline_data = AIRLINE_DOMAINS.get(airline_code)
    if airline_data:
        return airline_data[1]  # Return the airline name
    
    return None

def get_logo_url(airline_code, size='small'):
    """
    Get airline logo URL using free services
    
    Uses Google's favicon service to fetch airline logos from their official websites.
    This is a free alternative that doesn't require API keys.
    
    Args:
        airline_code: IATA/ICAO airline code (2-3 letters)
        size: Logo size (64, 128, 256, etc.) - Google favicon service supports various sizes
    
    Returns:
        str: URL to airline logo or None if not available
    """
    if not airline_code:
        return None
    
    airline_code = airline_code.upper()
    
    # Check if we have a domain mapping for this airline
    airline_data = AIRLINE_DOMAINS.get(airline_code)
    
    if airline_data:
        domain = airline_data[0]  # Get the domain
        # Use Google's favicon service (free, no API key required)
        # This fetches the favicon from the airline's official website
        size_map = {
            'small': 64,
            'medium': 128,
            'large': 256
        }
        icon_size = size_map.get(size, 128)
        return f"https://www.google.com/s2/favicons?domain={domain}&sz={icon_size}"
    
    # If no mapping exists, return None (graceful degradation)
    # The web interface will simply not display a logo
    return None

def get_airline_info(callsign):
    """
    Get airline code, name, and logo URL from callsign
    
    Args:
        callsign: Flight callsign string
    
    Returns:
        dict: {'code': airline_code, 'name': airline_name, 'logo_url': logo_url} or None
    """
    airline_code = extract_airline_code(callsign)
    if not airline_code:
        return None
    
    logo_url = get_logo_url(airline_code)
    airline_name = get_airline_name(airline_code)
    
    result = {
        'code': airline_code,
        'logo_url': logo_url
    }
    
    if airline_name:
        result['name'] = airline_name
    
    return result

if __name__ == '__main__':
    # Test the functions
    test_callsigns = ['DLH123', 'UAE456', 'BAW789', 'EWG1AN', 'QTR91Y']
    
    print("Testing airline code extraction:")
    for callsign in test_callsigns:
        info = get_airline_info(callsign)
        if info:
            name = info.get('name', 'N/A')
            print(f"{callsign:10} -> {info['code']:5} -> {name:30} -> {info['logo_url']}")
        else:
            print(f"{callsign:10} -> No airline code found")


