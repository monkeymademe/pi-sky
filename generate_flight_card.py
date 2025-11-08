#!/usr/bin/env python3
"""
Generate a flight card image (SVG/PNG) matching the design from index.html

This script creates a visual representation of a flight information card that matches
the design used in the flight tracker web interface (index.html). It can generate SVG 
files (always) and optionally PNG files (if cairosvg is installed).

The card includes:
- Header: Callsign, ICAO code, and airline logo (automatically fetched if callsign provided)
- Route section: Origin and destination airports with country flags
- Footer: Altitude, Speed, Track (always shown), plus optional fields:
  - Vertical rate, Distance, Squawk code
  - Location coordinates (full width)
  - Aircraft model/type/registration (full width)

Usage:
    # Generate with default dummy data
    python3 generate_flight_card.py
    
    # Generate with custom flight data
    python3 generate_flight_card.py --callsign "DLH456" --origin "BER" --destination "CDG" \
        --altitude 35000 --speed 450.5 --distance 2.8 --status saved
    
    # Generate both SVG and PNG
    python3 generate_flight_card.py --png
    
    # See all options
    python3 generate_flight_card.py --help

Examples:
    # Lufthansa flight from Berlin to Paris
    python3 generate_flight_card.py --callsign "DLH123" --origin "BER" --destination "CDG" \
        --origin-country "Germany" --destination-country "France" --status new
    
    # British Airways transatlantic flight
    python3 generate_flight_card.py --callsign "BAW789" --origin "LHR" --destination "JFK" \
        --origin-country "United Kingdom" --destination-country "United States" \
        --altitude 38000 --speed 520 --distance 3456
"""

import os
import sys
import base64
import requests
from datetime import datetime

# Try to import airline logo utilities
try:
    from airline_logos import get_airline_info
    HAS_AIRLINE_LOGOS = True
except ImportError:
    HAS_AIRLINE_LOGOS = False

def format_altitude(alt):
    """Format altitude with commas"""
    if alt is None:
        return 'N/A'
    return f"{alt:,} ft"

def format_speed(speed):
    """Format speed"""
    if speed is None:
        return 'N/A'
    return f"{speed:.1f} kts"

def format_distance(distance):
    """Format distance"""
    if distance is None:
        return 'N/A'
    if distance < 1:
        return f"{(distance * 1000):.0f} m"
    return f"{distance:.1f} km"

def format_track(track):
    """Format track/heading"""
    if track is None:
        return 'N/A'
    return f"{track:.1f}°"

def format_vertical_rate(rate):
    """Format vertical rate"""
    if rate is None:
        return 'N/A'
    sign = '+' if rate >= 0 else ''
    return f"{sign}{int(rate)} ft/min"

def format_coordinates(lat, lon):
    """Format coordinates"""
    if lat is None or lon is None:
        return 'N/A'
    return f"{lat:.5f}, {lon:.5f}"

def get_country_flag(country):
    """Map country names to flag emojis"""
    flags = {
        'Germany': '🇩🇪', 'United Kingdom': '🇬🇧', 'France': '🇫🇷',
        'Netherlands': '🇳🇱', 'Italy': '🇮🇹', 'Spain': '🇪🇸',
        'Austria': '🇦🇹', 'Switzerland': '🇨🇭', 'Denmark': '🇩🇰',
        'Sweden': '🇸🇪', 'Norway': '🇳🇴', 'Finland': '🇫🇮',
        'Poland': '🇵🇱', 'Czech Republic': '🇨🇿', 'Hungary': '🇭🇺',
        'Greece': '🇬🇷', 'Portugal': '🇵🇹', 'Ireland': '🇮🇪',
        'Belgium': '🇧🇪', 'Turkey': '🇹🇷', 'Croatia': '🇭🇷',
        'United Arab Emirates': '🇦🇪', 'Qatar': '🇶🇦', 'Saudi Arabia': '🇸🇦',
        'Israel': '🇮🇱', 'Singapore': '🇸🇬', 'Hong Kong': '🇭🇰',
        'Japan': '🇯🇵', 'South Korea': '🇰🇷', 'Thailand': '🇹🇭',
        'Malaysia': '🇲🇾', 'United States': '🇺🇸', 'China': '🇨🇳'
    }
    return flags.get(country, '🌍')

def generate_flight_card_svg(flight, output_path=None, inky_mode=False):
    """
    Generate an SVG flight card matching the design from index-maps.html
    
    Args:
        flight: dict with flight data
        output_path: Optional path to save SVG file (default: flight_card.svg)
        inky_mode: Whether to use Inky Impression 73 compatible colors
    
    Returns:
        str: SVG content
    """
    # Card dimensions (will adjust height based on content)
    card_width = 400
    base_card_height = 276  # Reduced by 4px since we removed the top border bar
    corner_radius = 12
    
    # Colors - use Inky-compatible colors if inky_mode is enabled
    if inky_mode:
        # Inky Impression 73 palette: black, white, red, green, blue, yellow
        header_gradient_start = '#0000FF'  # Blue
        header_gradient_end = '#0000FF'    # Blue (solid, no gradient on e-ink)
        airport_code_color = '#0000FF'     # Blue
        label_color = '#000000'            # Black
        country_color = '#000000'          # Black
        footer_gradient_start = '#FFFFFF'  # White
        footer_gradient_end = '#FFFFFF'    # White (solid)
    else:
        # Original colors
        header_gradient_start = '#667eea'
        header_gradient_end = '#764ba2'
        airport_code_color = '#667eea'
        label_color = '#000000'  # Changed from light gray to black
        country_color = '#000000'  # Changed from gray to black
        footer_gradient_start = '#f3f4f6'
        footer_gradient_end = '#e5e7eb'
    
    # Flight data with defaults
    callsign = flight.get('callsign', 'N/A')
    icao = flight.get('icao', 'TEST01')
    origin = flight.get('origin', '---')
    destination = flight.get('destination', '---')
    origin_country = flight.get('origin_country', '')
    destination_country = flight.get('destination_country', '')
    altitude = flight.get('altitude', 0)
    speed = flight.get('speed', 0)
    track = flight.get('track', None)
    vertical_rate = flight.get('vertical_rate', None)
    distance = flight.get('distance', None)
    squawk = flight.get('squawk', None)
    lat = flight.get('lat', None)
    lon = flight.get('lon', None)
    aircraft_model = flight.get('aircraft_model', None)
    aircraft_type = flight.get('aircraft_type', None)
    aircraft_registration = flight.get('aircraft_registration', None)
    airline_logo = flight.get('airline_logo', None)
    airline_code = flight.get('airline_code', None)
    airline_name = flight.get('airline_name', None)
    status = flight.get('status', 'saved')  # 'new' or 'saved' (no longer used for border, but kept for future use)
    
    # Calculate footer items first to determine card height
    # Always include all fields - show "N/A" if data is missing
    footer_items = []
    footer_items.append(('Altitude', format_altitude(altitude)))
    footer_items.append(('Speed', format_speed(speed)))
    footer_items.append(('Track', format_track(track)))
    
    # Always include optional fields (show N/A if not provided)
    if vertical_rate is not None:
        footer_items.append(('Vertical', format_vertical_rate(vertical_rate)))
    else:
        footer_items.append(('Vertical', 'N/A'))
    
    if distance is not None:
        footer_items.append(('Distance', format_distance(distance)))
    else:
        footer_items.append(('Distance', 'N/A'))
    
    if squawk:
        footer_items.append(('Squawk', squawk))
    else:
        footer_items.append(('Squawk', 'N/A'))
    
    # Calculate how many full-width items we'll have
    # Always include Location and Aircraft fields (show N/A if not provided)
    full_width_items = 2  # Always show Location and Aircraft
    
    # Calculate grid layout
    items_per_row = 3
    footer_row_height = 40
    num_grid_rows = (len(footer_items) + items_per_row - 1) // items_per_row
    footer_height = 16 + (num_grid_rows * footer_row_height) + (full_width_items * footer_row_height)
    
    # Adjust card height based on footer content
    card_height = base_card_height + max(0, footer_height - 66)  # 66 is base footer height
    
    # Prepare logo clip path if needed
    logo_clip_needed = False
    airline_logo_url = airline_logo
    airline_code_val = airline_code
    airline_name_val = airline_name
    
    # If no logo URL but we have airline info module and callsign, try to get logo
    if not airline_logo_url and HAS_AIRLINE_LOGOS and callsign and callsign != 'N/A':
        try:
            airline_info = get_airline_info(callsign)
            if airline_info:
                airline_logo_url = airline_info.get('logo_url')
                if not airline_code_val:
                    airline_code_val = airline_info.get('code')
                if not airline_name_val:
                    airline_name_val = airline_info.get('name')
        except:
            pass
    
    if airline_logo_url or airline_code_val:
        logo_clip_needed = True
    
    # Start building SVG
    svg = f'''<svg width="{card_width}" height="{card_height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <!-- Header gradient -->
        <linearGradient id="headerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:{header_gradient_start};stop-opacity:1" />
            <stop offset="100%" style="stop-color:{header_gradient_end};stop-opacity:1" />
        </linearGradient>
        <!-- Footer gradient -->
        <linearGradient id="footerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:{footer_gradient_start};stop-opacity:1" />
            <stop offset="100%" style="stop-color:{footer_gradient_end};stop-opacity:1" />
        </linearGradient>
        <!-- Plane line gradient -->
        <linearGradient id="planeLineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" style="stop-color:{airport_code_color};stop-opacity:1" />
            <stop offset="50%" style="stop-color:{airport_code_color};stop-opacity:0" />
            <stop offset="100%" style="stop-color:{airport_code_color};stop-opacity:1" />
        </linearGradient>'''
    
    # Calculate header vertical positions (for centering content) - do this before building SVG
    header_height = 70
    header_center_y = header_height / 2  # 35px
    # Move callsign and ICAO down a bit for better vertical centering
    callsign_baseline = header_center_y + 2  # Slightly below center for better visual balance
    icao_baseline = callsign_baseline + 18  # ~18px below callsign baseline
    logo_center_y = header_center_y
    logo_y = logo_center_y - 16  # Logo is 32px tall, so y position is center - 16
    
    if logo_clip_needed:
        svg += f'''
        <!-- Logo clip path -->
        <clipPath id="logoClip">
            <rect width="32" height="32" rx="4"/>
        </clipPath>'''
    
    svg += f'''
    </defs>
    
    <!-- Card background with rounded corners -->
    <rect width="{card_width}" height="{card_height}" rx="{corner_radius}" ry="{corner_radius}" 
          fill="white"/>
    
    <!-- Header section with rounded top corners -->
    <path d="M 0,{corner_radius} Q 0,0 {corner_radius},0 L {card_width - corner_radius},0 Q {card_width},0 {card_width},{corner_radius} L {card_width},70 L 0,70 Z" 
          fill="url(#headerGradient)"/>
    
    <!-- Callsign (vertically centered) -->
    <text x="20" y="{callsign_baseline}" font-family="system-ui, -apple-system, sans-serif" font-size="26" 
          font-weight="bold" fill="white">{callsign}</text>
    
    <!-- ICAO code (vertically centered) -->
    <text x="20" y="{icao_baseline}" font-family="monospace" font-size="14" fill="white" opacity="0.9">{icao}</text>
    
    <!-- Airline logo (if available) -->
    '''
    
    if airline_logo_url:
        # Try to fetch and embed logo as data URI (for better compatibility)
        try:
            response = requests.get(airline_logo_url, timeout=5)
            if response.status_code == 200:
                # Determine image type
                content_type = response.headers.get('content-type', 'image/png')
                if 'png' in content_type:
                    img_ext = 'png'
                elif 'jpeg' in content_type or 'jpg' in content_type:
                    img_ext = 'jpeg'
                elif 'svg' in content_type:
                    img_ext = 'svg+xml'
                else:
                    img_ext = 'png'
                
                # Encode as base64
                img_data = base64.b64encode(response.content).decode('utf-8')
                data_uri = f"data:image/{img_ext};base64,{img_data}"
                
                svg += f'''    <!-- Airline logo (embedded, vertically centered) -->
    <g transform="translate({card_width - 52}, {logo_y})" clip-path="url(#logoClip)">
        <image x="0" y="0" width="32" height="32" href="{data_uri}" 
               preserveAspectRatio="xMidYMid meet"/>
    </g>
    '''
            else:
                # Fallback to placeholder
                svg += f'''    <!-- Airline logo placeholder (URL failed to load) -->
    <rect x="{card_width - 52}" y="{logo_y}" width="32" height="32" rx="4" fill="rgba(255,255,255,0.2)"/>
    <text x="{card_width - 36}" y="{logo_center_y + 4}" font-family="system-ui" font-size="9" fill="white" text-anchor="middle" opacity="0.8">{airline_code_val or 'LOGO'}</text>
    '''
        except:
            # Fallback to external image reference or placeholder
            # Use external image reference (may not work in all SVG viewers)
            svg += f'''    <!-- Airline logo (external reference, vertically centered) -->
    <g transform="translate({card_width - 52}, {logo_y})" clip-path="url(#logoClip)">
        <image x="0" y="0" width="32" height="32" href="{airline_logo_url}" 
               preserveAspectRatio="xMidYMid meet"/>
    </g>
    '''
    elif airline_code_val:
        # Show airline code as text if no logo
        svg += f'''    <!-- Airline code (no logo available) -->
    <rect x="{card_width - 52}" y="{logo_y}" width="32" height="32" rx="4" fill="rgba(255,255,255,0.2)"/>
    <text x="{card_width - 36}" y="{logo_center_y + 4}" font-family="system-ui" font-size="10" fill="white" text-anchor="middle" opacity="0.9" font-weight="bold">{airline_code_val[:3]}</text>
    '''
    
    svg += f'''
    
    <!-- Route section (middle) - padding: 24px 20px like index.html -->
    <rect x="0" y="70" width="{card_width}" height="140" fill="white"/>
    
    <!-- Calculate vertical positions based on CSS:
         Route section: 24px top padding, so content starts at y=98
         Label has margin-bottom: 8px, airport code margin-bottom: 4px
         All columns vertically centered (align-items: center)
         Center of route section is approximately y=144 -->
    '''
    
    # Vertical positioning (matching index.html CSS)
    # Route section: starts at y=70, height=140, so ends at y=210
    # Padding: 24px top/bottom (24px from top = y=94, 24px from bottom = y=186)
    # All columns are vertically centered (align-items: center)
    # The center point for alignment is the middle of the content area
    route_content_top = 70 + 24  # 94 (after top padding)
    route_content_bottom = 210 - 24  # 186 (before bottom padding)
    route_center_y = (route_content_top + route_content_bottom) / 2  # 140 (center of content area)
    
    # Airport code is the main centered element (40px font)
    # SVG text y-coordinate is the baseline
    # To align visual center with route_center_y (140), we need to account for font metrics
    # For system fonts, 40px text has approximate ascent ~28px, descent ~12px
    # Visual center ≈ baseline - (ascent - descent)/2 ≈ baseline - 8px
    # So if visual center = 140, baseline ≈ 148
    airport_code_y = route_center_y + 8  # Baseline for airport code (148) - visual center aligns with plane (140)
    
    # Label: font-size 11px, margin-bottom: 8px (from CSS)
    # Airport code visual top ≈ airport_code_y - 28 ≈ 152 - 28 = 124
    # Label needs 8px margin below it, so label bottom ≈ 124 - 8 = 116
    # Label height ≈ 8px, so label baseline ≈ 116 - 4 ≈ 112
    # But let's be more precise: label baseline = airport code top - 8px margin - label ascent
    label_y = airport_code_y - 28 - 8 - 4  # 152 - 28 - 8 - 4 = 112
    
    # Country: font-size 14px, margin-top: 4px (from airport code margin-bottom in CSS)
    # Airport code visual bottom ≈ airport_code_y + 12 ≈ 152 + 12 = 164
    # Country needs 4px margin above it, so country top ≈ 164 + 4 = 168
    # Country height ≈ 10px, so country baseline ≈ 168 + 5 ≈ 173
    country_y = airport_code_y + 12 + 4 + 5  # 152 + 12 + 4 + 5 = 173
    
    # Origin section
    svg += f'''    <!-- Origin section -->
    <text x="20" y="{label_y}" font-family="system-ui, -apple-system, sans-serif" font-size="11" 
          fill="{label_color}" text-transform="uppercase" letter-spacing="0.5">From</text>
    <text x="20" y="{airport_code_y}" font-family="system-ui, -apple-system, sans-serif" font-size="40" 
          font-weight="bold" fill="{airport_code_color}">{origin}</text>
    '''
    
    # Origin country if available
    if origin_country:
        # Just show country name without flag emoji for better compatibility
        svg += f'''    <text x="20" y="{country_y}" font-family="system-ui, -apple-system, sans-serif" font-size="14" 
          fill="{country_color}">{origin_country}</text>
    '''
    
    # Destination section
    svg += f'''    <!-- Destination section -->
    <text x="{card_width - 20}" y="{label_y}" font-family="system-ui, -apple-system, sans-serif" font-size="11" 
          fill="{label_color}" text-anchor="end" text-transform="uppercase" letter-spacing="0.5">To</text>
    <text x="{card_width - 20}" y="{airport_code_y}" font-family="system-ui, -apple-system, sans-serif" font-size="40" 
          font-weight="bold" fill="{airport_code_color}" text-anchor="end">{destination}</text>
    '''
    
    # Destination country if available
    if destination_country:
        # Just show country name without flag emoji for better compatibility
        svg += f'''    <text x="{card_width - 20}" y="{country_y}" font-family="system-ui, -apple-system, sans-serif" font-size="14" 
          fill="{country_color}" text-anchor="end">{destination_country}</text>
    '''
    
    # Plane icon in center - align with airport codes (vertically centered)
    plane_center_x = card_width / 2
    plane_center_y = route_center_y  # 144
    plane_size = 48
    plane_icon_size = 24  # ViewBox size for plane icon
    
    # Dashed line behind plane (width matches plane container padding)
    # Plane container has padding: 0 8px, and the line should span the width
    # Grid gap is 16px, so line should span from edge of origin to edge of destination sections
    line_left = 20 + 100  # Approximate left edge (origin section ends around here)
    line_right = card_width - 20 - 100  # Approximate right edge (destination section starts around here)
    svg += f'''    <!-- Plane route line -->
    <line x1="{line_left}" y1="{plane_center_y}" x2="{line_right}" y2="{plane_center_y}" 
          stroke="{airport_code_color}" stroke-width="1" stroke-dasharray="5,5" opacity="0.5"/>
    
    <!-- Plane icon background circle -->
    <circle cx="{plane_center_x}" cy="{plane_center_y}" r="{plane_size/2}" fill="white"/>
    
    <!-- Plane icon (scaled 2x from 24x24 viewBox, centered) -->
    <g transform="translate({plane_center_x}, {plane_center_y}) scale(2) translate(-12, -12)">
        <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" 
              fill="{airport_code_color}"/>
    </g>
    
    <!-- Footer section with rounded bottom corners (dynamic height) -->
    <path d="M 0,210 L 0,{card_height - corner_radius} Q 0,{card_height} {corner_radius},{card_height} L {card_width - corner_radius},{card_height} Q {card_width},{card_height} {card_width},{card_height - corner_radius} L {card_width},210 Z" 
          fill="url(#footerGradient)"/>
    
    <!-- Border line at top of footer -->
    <line x1="0" y1="210" x2="{card_width}" y2="210" stroke="#e5e7eb" stroke-width="1"/>
    
    <!-- Footer details grid (auto-fit layout like index.html) -->
    <g>'''
    
    # Calculate grid layout (already calculated above, but need item_width and footer_start_y)
    item_width = (card_width - 40 - (items_per_row - 1) * 16) / items_per_row  # 40px padding, 16px gap
    footer_start_y = 231  # Adjusted: footer starts at y=210, +21px padding = 231
    
    for i, (label, value) in enumerate(footer_items):
        row = i // items_per_row
        col = i % items_per_row
        x = 20 + col * (item_width + 16)
        y = footer_start_y + row * footer_row_height
        
        # Label
        # Use monospace font for Squawk, system-ui for others
        value_font_family = 'monospace' if label == 'Squawk' else 'system-ui, -apple-system, sans-serif'
        svg += f'''
        <text x="{x}" y="{y}" font-family="system-ui, -apple-system, sans-serif" font-size="11" 
              fill="{label_color}" text-transform="uppercase" letter-spacing="0.5">{label}</text>
        <text x="{x}" y="{y + 20}" font-family="{value_font_family}" font-size="16" 
              font-weight="bold" fill="#1f2937">{value}</text>'''
    
    # Location (always shown, full width) - goes after grid items
    coord_y = footer_start_y + num_grid_rows * footer_row_height
    if lat is not None and lon is not None:
        location_value = format_coordinates(lat, lon)
    else:
        location_value = 'N/A'
    svg += f'''
        <text x="20" y="{coord_y}" font-family="system-ui, -apple-system, sans-serif" font-size="11" 
              fill="{label_color}" text-transform="uppercase" letter-spacing="0.5">Location</text>
        <text x="20" y="{coord_y + 20}" font-family="monospace" font-size="14" 
              font-weight="bold" fill="#1f2937">{location_value}</text>'''
    
    # Aircraft info (always shown, full width) - goes after location
    aircraft_y = footer_start_y + num_grid_rows * footer_row_height + footer_row_height
    if aircraft_model or aircraft_type:
        aircraft_text = aircraft_model or aircraft_type or 'N/A'
        if aircraft_registration:
            aircraft_text += f" ({aircraft_registration})"
    else:
        aircraft_text = 'N/A'
    svg += f'''
        <text x="20" y="{aircraft_y}" font-family="system-ui, -apple-system, sans-serif" font-size="11" 
              fill="{label_color}" text-transform="uppercase" letter-spacing="0.5">Aircraft</text>
        <text x="20" y="{aircraft_y + 20}" font-family="system-ui, -apple-system, sans-serif" font-size="16" 
              font-weight="bold" fill="#1f2937">{aircraft_text}</text>'''
    
    svg += '''
    </g>
</svg>'''
    
    # Save to file if output_path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg)
        print(f"Flight card saved to: {output_path}")
    
    return svg

def main():
    """Generate a test flight card with dummy data"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate a flight card image (SVG/PNG)')
    parser.add_argument('--output', '-o', default='test_flight.svg',
                       help='Output file path (default: test_flight.svg)')
    parser.add_argument('--callsign', default='DLH456', help='Flight callsign')
    parser.add_argument('--icao', default='4CA123', help='ICAO code')
    parser.add_argument('--origin', default='BER', help='Origin airport code')
    parser.add_argument('--destination', default='CDG', help='Destination airport code')
    parser.add_argument('--origin-country', default='Germany', help='Origin country')
    parser.add_argument('--destination-country', default='France', help='Destination country')
    parser.add_argument('--altitude', type=int, default=35000, help='Altitude in feet')
    parser.add_argument('--speed', type=float, default=450.5, help='Speed in knots')
    parser.add_argument('--track', type=float, help='Track/heading in degrees')
    parser.add_argument('--vertical-rate', type=int, help='Vertical rate in ft/min')
    parser.add_argument('--distance', type=float, help='Distance in km')
    parser.add_argument('--squawk', help='Squawk code')
    parser.add_argument('--lat', type=float, help='Latitude')
    parser.add_argument('--lon', type=float, help='Longitude')
    parser.add_argument('--aircraft-model', help='Aircraft model')
    parser.add_argument('--aircraft-type', help='Aircraft type')
    parser.add_argument('--aircraft-registration', help='Aircraft registration')
    parser.add_argument('--airline-logo', help='Airline logo URL')
    parser.add_argument('--airline-code', help='Airline code (IATA/ICAO)')
    parser.add_argument('--airline-name', help='Airline name')
    parser.add_argument('--status', choices=['new', 'saved'], default='saved', 
                       help='Flight status (new or saved)')
    parser.add_argument('--png', action='store_true', help='Also generate PNG file')
    
    args = parser.parse_args()
    
    # Flight data
    flight = {
        'callsign': args.callsign,
        'icao': args.icao,
        'origin': args.origin,
        'destination': args.destination,
        'origin_country': args.origin_country,
        'destination_country': args.destination_country,
        'altitude': args.altitude,
        'speed': args.speed,
        'track': args.track,
        'vertical_rate': args.vertical_rate,
        'distance': args.distance,
        'squawk': args.squawk,
        'lat': args.lat,
        'lon': args.lon,
        'aircraft_model': args.aircraft_model,
        'aircraft_type': args.aircraft_type,
        'aircraft_registration': args.aircraft_registration,
        'airline_logo': args.airline_logo,
        'airline_code': args.airline_code,
        'airline_name': args.airline_name,
        'status': args.status
    }
    
    # Generate SVG
    svg_content = generate_flight_card_svg(flight, args.output)
    
    print(f"Generated flight card SVG: {args.output}")
    print(f"\nFlight details:")
    print(f"  Callsign: {flight['callsign']}")
    print(f"  ICAO: {flight['icao']}")
    print(f"  Route: {flight['origin']} → {flight['destination']}")
    print(f"  Altitude: {format_altitude(flight['altitude'])}")
    print(f"  Speed: {format_speed(flight['speed'])}")
    if flight.get('track') is not None:
        print(f"  Track: {format_track(flight['track'])}")
    if flight.get('vertical_rate') is not None:
        print(f"  Vertical Rate: {format_vertical_rate(flight['vertical_rate'])}")
    if flight.get('distance') is not None:
        print(f"  Distance: {format_distance(flight['distance'])}")
    if flight.get('squawk'):
        print(f"  Squawk: {flight['squawk']}")
    print(f"  Status: {flight['status']}")
    
    # Optionally generate PNG if cairosvg is available
    if args.png:
        try:
            import cairosvg
            if args.output.endswith('.svg'):
                png_file = args.output.replace('.svg', '.png')
            else:
                png_file = args.output + '.png'
            cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), write_to=png_file, output_width=800)
            print(f"\nAlso generated PNG: {png_file}")
        except ImportError:
            print("\nError: cairosvg is not installed. Install it with:")
            print("  pip install cairosvg")
    else:
        print("\nTip: Use --png flag to also generate a PNG file")
        print("  (requires: pip install cairosvg)")

if __name__ == '__main__':
    main()

