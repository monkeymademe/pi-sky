#!/usr/bin/env python3
"""
Generate a flight card image (SVG/PNG) matching the design from the web UI.

This module is imported by `map_to_png.py` to overlay a "flight card" onto the
generated inky-ready PNG output.
"""

import base64
import requests

# Try to import airline logos module
try:
    from airline_logos import get_airline_info
    HAS_AIRLINE_LOGOS = True
except Exception:
    HAS_AIRLINE_LOGOS = False


def format_altitude(alt):
    """Format altitude with commas"""
    if not alt:
        return 'n/a'
    return f"{int(alt):,} ft"


def format_speed(speed):
    """Format speed"""
    if not speed:
        return 'n/a'
    return f"{speed:.1f} kts"


def format_distance(distance):
    """Format distance"""
    if distance is None:
        return 'n/a'
    if distance < 1:
        return f"{(distance * 1000):.0f} m"
    return f"{distance:.1f} km"


def format_track(track):
    """Format track/heading"""
    if track is None:
        return 'n/a'
    return f"{track:.1f}°"


def format_vertical_rate(rate):
    """Format vertical rate"""
    if rate is None:
        return 'n/a'
    sign = '+' if rate >= 0 else ''
    return f"{sign}{int(round(rate))} ft/min"


def format_coordinates(lat, lon):
    """Format coordinates"""
    if lat is None or lon is None:
        return 'n/a'
    return f"{lat:.5f}, {lon:.5f}"


def _vertical_rate_icon_angle(rate):
    """Match index.html: simple up/down/level visual."""
    try:
        if rate is None:
            return 0
        numeric = float(rate)
        if abs(numeric) < 100:
            return 0
        return -18 if numeric > 0 else 18
    except Exception:
        return 0


def get_country_flag(country):
    """Map country names to flag emojis"""
    flags = {
        'Germany': '🇩🇪',
        'United Kingdom': '🇬🇧',
        'France': '🇫🇷',
        'Netherlands': '🇳🇱',
        'Italy': '🇮🇹',
        'Spain': '🇪🇸',
        'Austria': '🇦🇹',
        'Switzerland': '🇨🇭',
        'Denmark': '🇩🇰',
        'Sweden': '🇸🇪',
        'Norway': '🇳🇴',
        'Finland': '🇫🇮',
        'Poland': '🇵🇱',
        'Czech Republic': '🇨🇿',
        'Hungary': '🇭🇺',
        'Greece': '🇬🇷',
        'Portugal': '🇵🇹',
        'Ireland': '🇮🇪',
        'Belgium': '🇧🇪',
        'Turkey': '🇹🇷',
        'Croatia': '🇭🇷',
        'United Arab Emirates': '🇦🇪',
        'Qatar': '🇶🇦',
        'Saudi Arabia': '🇸🇦',
        'Israel': '🇮🇱',
        'Singapore': '🇸🇬',
        'Hong Kong': '🇭🇰',
        'Japan': '🇯🇵',
        'South Korea': '🇰🇷',
        'Thailand': '🇹🇭',
        'Malaysia': '🇲🇾',
        'United States': '🇺🇸',
        'China': '🇨🇳',
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
    card_width = 400
    base_card_height = 276
    corner_radius = 12

    # Colors - use Inky-compatible colors if inky_mode is enabled
    if inky_mode:
        header_gradient_start = '#0000FF'
        header_gradient_end = '#0000FF'
        airport_code_color = '#0000FF'
        label_color = '#000000'
        country_color = '#000000'
        footer_gradient_start = '#FFFFFF'
        footer_gradient_end = '#FFFFFF'
    else:
        header_gradient_start = '#667eea'
        header_gradient_end = '#764ba2'
        airport_code_color = '#667eea'
        label_color = '#000000'
        country_color = '#000000'
        footer_gradient_start = '#f3f4f6'
        footer_gradient_end = '#e5e7eb'

    # Extract flight data
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
    status = flight.get('status', 'saved')

    # Footer layout matches web/index.html (3-column grid with spans + icon cell)
    items_per_row = 3
    footer_row_height = 40
    footer_rows = 5  # Position/Distance, Alt/Speed/Track, Vert+Icon, Tail+Squawk, Aircraft
    footer_top = 210
    footer_padding_y = 16
    card_height = footer_top + footer_padding_y + (footer_rows * footer_row_height) + footer_padding_y

    # Check for airline logo
    logo_clip_needed = False
    airline_logo_url = None
    airline_code_val = None

    if HAS_AIRLINE_LOGOS:
        airline_info = get_airline_info(callsign)
        if airline_info:
            airline_logo_url = airline_info.get('logo_url')
            airline_code_val = airline_info.get('code')
            if airline_logo_url:
                logo_clip_needed = True

    # Build SVG
    svg = '<svg width="' + str(card_width) + '" height="' + str(card_height) + \
          '" xmlns="http://www.w3.org/2000/svg">\n' + \
          '    <defs>\n' + \
          '        <!-- Header gradient -->\n' + \
          '        <linearGradient id="headerGradient" x1="0%" y1="0%" x2="100%" y2="100%">\n' + \
          '            <stop offset="0%" style="stop-color:' + header_gradient_start + ';stop-opacity:1" />\n' + \
          '            <stop offset="100%" style="stop-color:' + header_gradient_end + ';stop-opacity:1" />\n' + \
          '        </linearGradient>\n' + \
          '        <!-- Footer gradient -->\n' + \
          '        <linearGradient id="footerGradient" x1="0%" y1="0%" x2="100%" y2="100%">\n' + \
          '            <stop offset="0%" style="stop-color:' + footer_gradient_start + ';stop-opacity:1" />\n' + \
          '            <stop offset="100%" style="stop-color:' + footer_gradient_end + ';stop-opacity:1" />\n' + \
          '        </linearGradient>\n' + \
          '        <!-- Plane line gradient -->\n' + \
          '        <linearGradient id="planeLineGradient" x1="0%" y1="0%" x2="100%" y2="0%">\n' + \
          '            <stop offset="0%" style="stop-color:' + airport_code_color + ';stop-opacity:1" />\n' + \
          '            <stop offset="50%" style="stop-color:' + airport_code_color + ';stop-opacity:0" />\n' + \
          '            <stop offset="100%" style="stop-color:' + airport_code_color + ';stop-opacity:1" />\n' + \
          '        </linearGradient>'

    if logo_clip_needed:
        svg += '\n        <!-- Logo clip path -->\n' + \
               '        <clipPath id="logoClip">\n' + \
               '            <rect width="32" height="32" rx="4"/>\n' + \
               '        </clipPath>'

    svg += '\n    </defs>\n' + \
           '    \n' + \
           '    <!-- Card background with rounded corners -->\n' + \
           '    <rect width="' + str(card_width) + '" height="' + str(card_height) + '" rx="' + str(corner_radius) + '" ry="' + str(corner_radius) + '" \n' + \
           '          fill="white"/>\n' + \
           '    \n' + \
           '    <!-- Header section with rounded top corners -->\n' + \
           '    <path d="M 0,' + str(corner_radius) + ' Q 0,0 ' + str(corner_radius) + ',0 L ' + str(card_width - corner_radius) + ',0 Q ' + str(card_width) + ',0 ' + str(card_width) + ',' + str(corner_radius) + ' L ' + str(card_width) + ',70 L 0,70 Z" \n' + \
           '          fill="url(#headerGradient)"/>\n'

    # Header text
    header_height = 70
    header_center_y = header_height / 2
    callsign_baseline = header_center_y + 5
    icao_baseline = callsign_baseline + 18

    svg += '    \n' + \
           '    <!-- Callsign (vertically centered) -->\n' + \
           '    <text x="20" y="' + str(callsign_baseline) + '" font-family="system-ui, -apple-system, sans-serif" font-size="26" \n' + \
           '          font-weight="bold" fill="white">' + str(callsign) + '</text>\n' + \
           '    \n' + \
           '    <!-- ICAO code (vertically centered) -->\n' + \
           '    <text x="20" y="' + str(icao_baseline) + '" font-family="monospace" font-size="14" fill="white" opacity="0.9">' + str(icao) + '</text>\n' + \
           '    \n' + \
           '    <!-- Airline logo (if available) -->\n    '

    # Airline logo section
    logo_center_y = header_center_y
    logo_y = logo_center_y - 16  # Center 32px logo vertically

    if airline_logo_url:
        # Try to download and embed the logo
        try:
            response = requests.get(airline_logo_url, timeout=5)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', 'image/png')
                if 'png' in content_type:
                    img_ext = 'png'
                elif 'jpeg' in content_type or 'jpg' in content_type:
                    img_ext = 'jpeg'
                elif 'svg' in content_type:
                    img_ext = 'svg+xml'
                else:
                    img_ext = 'png'

                img_data = base64.b64encode(response.content).decode('utf-8')
                data_uri = 'data:image/' + img_ext + ';base64,' + img_data

                svg += '    <!-- Airline logo (embedded, vertically centered) -->\n' + \
                       '    <g transform="translate(' + str(card_width - 52) + ', ' + str(logo_y) + ')" clip-path="url(#logoClip)">\n' + \
                       '        <image x="0" y="0" width="32" height="32" href="' + data_uri + '" \n' + \
                       '               preserveAspectRatio="xMidYMid meet"/>\n' + \
                       '    </g>\n    '
        except Exception:
            pass
    elif airline_code_val:
        # Show airline code instead of logo
        svg += '    <!-- Airline code (no logo available) -->\n' + \
               '    <rect x="' + str(card_width - 52) + '" y="' + str(logo_y) + '" width="32" height="32" rx="4" fill="rgba(255,255,255,0.2)"/>\n' + \
               '    <text x="' + str(card_width - 36) + '" y="' + str(logo_y + 20) + '" font-family="system-ui" font-size="10" fill="white" text-anchor="middle" opacity="0.9" font-weight="bold">' + str(airline_code_val) + '</text>\n    '

    # Route section
    svg += '\n    \n' + \
           '    <!-- Route section (middle) -->\n' + \
           '    <rect x="0" y="70" width="' + str(card_width) + '" height="140" fill="white"/>\n'

    route_content_top = 70 + 24
    route_content_bottom = 70 + 140 - 24
    route_center_y = (route_content_top + route_content_bottom) / 2

    airport_code_y = route_center_y + 8
    label_y = airport_code_y - 28 - 8 - 4
    country_y = airport_code_y + 20 + 4

    # Origin section
    svg += '\n    <!-- Origin section -->\n' + \
           '    <text x="20" y="' + str(label_y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="11" \n' + \
           '          fill="' + label_color + '" text-transform="uppercase" letter-spacing="0.5">From</text>\n' + \
           '    <text x="20" y="' + str(airport_code_y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="40" \n' + \
           '          font-weight="bold" fill="' + airport_code_color + '">' + str(origin) + '</text>\n'

    if origin_country:
        svg += '    <text x="20" y="' + str(country_y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="14" \n' + \
               '          fill="' + country_color + '">' + origin_country + '</text>\n'

    # Destination section
    svg += '    <!-- Destination section -->\n' + \
           '    <text x="' + str(card_width - 20) + '" y="' + str(label_y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="11" \n' + \
           '          fill="' + label_color + '" text-anchor="end" text-transform="uppercase" letter-spacing="0.5">To</text>\n' + \
           '    <text x="' + str(card_width - 20) + '" y="' + str(airport_code_y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="40" \n' + \
           '          font-weight="bold" fill="' + airport_code_color + '" text-anchor="end">' + str(destination) + '</text>\n'

    if destination_country:
        svg += '    <text x="' + str(card_width - 20) + '" y="' + str(country_y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="14" \n' + \
               '          fill="' + country_color + '" text-anchor="end">' + destination_country + '</text>\n'

    # Plane route line and plane icon
    plane_center_x = card_width / 2
    plane_center_y = route_center_y
    line_left = 120
    line_right = card_width - 120

    svg += '    <!-- Plane route line -->\n' + \
           '    <line x1="' + str(line_left) + '" y1="' + str(plane_center_y) + '" x2="' + str(line_right) + '" y2="' + str(plane_center_y) + '" \n' + \
           '          stroke="' + airport_code_color + '" stroke-width="1" stroke-dasharray="5,5" opacity="0.5"/>\n' + \
           '    <!-- Plane icon background circle -->\n' + \
           '    <circle cx="' + str(plane_center_x) + '" cy="' + str(plane_center_y) + '" r="24" fill="white"/>\n' + \
           '    <!-- Plane icon -->\n' + \
           '    <g transform="translate(' + str(plane_center_x) + ', ' + str(plane_center_y) + ') scale(2) translate(-12, -12)">\n' + \
           '        <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" \n' + \
           '              fill="' + airport_code_color + '"/>\n' + \
           '    </g>\n'

    # Footer section
    svg += '    <!-- Footer section (matches index.html footer grid) -->\n' + \
           '    <path d="M 0,210 L 0,' + str(card_height - corner_radius) + ' Q 0,' + str(card_height) + ' ' + str(corner_radius) + ',' + str(card_height) + \
           ' L ' + str(card_width - corner_radius) + ',' + str(card_height) + ' Q ' + str(card_width) + ',' + str(card_height) + ' ' + str(card_width) + ',' + str(card_height - corner_radius) + \
           ' L ' + str(card_width) + ',210 Z" \n' + \
           '          fill="url(#footerGradient)"/>\n' + \
           '    <line x1="0" y1="210" x2="' + str(card_width) + '" y2="210" stroke="#e5e7eb" stroke-width="1"/>\n' + \
           '    <g>'

    item_width = (card_width - 40 - (items_per_row - 1) * 16) / items_per_row
    col1_x = 20
    col2_x = 20 + (item_width + 16)
    col3_x = 20 + (2 * (item_width + 16))
    footer_start_y = 231  # 210 + 21 (matches legacy spacing)

    value_color = '#000000' if inky_mode else '#1f2937'
    icon_color = '#000000' if inky_mode else '#3d5066'

    position_value = format_coordinates(lat, lon) if lat is not None and lon is not None else 'n/a'
    distance_value = format_distance(distance) if distance is not None else 'n/a'
    altitude_value = format_altitude(altitude)
    speed_value = format_speed(speed)
    track_value = format_track(track) if track is not None else 'n/a'
    vertical_value = format_vertical_rate(vertical_rate) if vertical_rate is not None else 'n/a'
    tail_value = aircraft_registration or 'n/a'
    squawk_value = squawk or 'n/a'
    aircraft_value = (aircraft_model or aircraft_type) or 'n/a'

    def _item(x, y, label, value, mono=False, value_size=16):
        vf = 'monospace' if mono else 'system-ui, -apple-system, sans-serif'
        return (
            '\n        <text x="' + str(x) + '" y="' + str(y) + '" font-family="system-ui, -apple-system, sans-serif" font-size="11" '
            '\n              fill="' + label_color + '" text-transform="uppercase" letter-spacing="0.5">' + str(label) + '</text>'
            '\n        <text x="' + str(x) + '" y="' + str(y + 20) + '" font-family="' + vf + '" font-size="' + str(value_size) + '" '
            '\n              font-weight="bold" fill="' + value_color + '">' + str(value) + '</text>'
        )

    # Row 0: Position (span 2 cols) + Distance
    svg += _item(col1_x, footer_start_y, 'Position', position_value, mono=True, value_size=14)
    svg += _item(col3_x, footer_start_y, 'Distance', distance_value)

    # Row 1: Altitude / Speed / Track
    y1 = footer_start_y + footer_row_height
    svg += _item(col1_x, y1, 'Altitude', altitude_value)
    svg += _item(col2_x, y1, 'Speed', speed_value)
    svg += _item(col3_x, y1, 'Track', track_value)

    # Row 2: Vertical Rate + icon cell (span 2 cols)
    y2 = footer_start_y + (2 * footer_row_height)
    svg += _item(col1_x, y2, 'Vertical Rate', vertical_value)

    # Plane-side icon (from web/assets/plane-side.svg), rotated like index.html
    angle = _vertical_rate_icon_angle(vertical_rate)
    icon_box_x = col2_x
    icon_center_x = icon_box_x + 26
    icon_center_y = y2 + 17
    svg += (
        '\n        <g transform="translate(' + str(icon_center_x) + ',' + str(icon_center_y) + ') rotate(' + str(angle) + ') translate(-12,-12)">'
        '\n            <path d="M10.5,15.9h10c.8,0,1.5-.7,1.5-1.5s-.7-1.5-1.5-1.5h-5.5l-4-4.8h-2s1.5,4.8,1.5,4.8h-5.5l-1.5-2h-1.5l1,3.5.4,1.5h1.6s5.5,0,5.5,0h0Z" fill="' + icon_color + '"/>'
        '\n        </g>'
    )

    # Row 3: Tail Number / Squawk
    y3 = footer_start_y + (3 * footer_row_height)
    svg += _item(col1_x, y3, 'Tail Number', tail_value)
    svg += _item(col2_x, y3, 'Squawk', squawk_value)

    # Row 4: Aircraft (full width)
    y4 = footer_start_y + (4 * footer_row_height)
    svg += _item(col1_x, y4, 'Aircraft', aircraft_value)

    svg += '\n    </g>\n</svg>'

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg)

    return svg

