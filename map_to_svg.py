#!/usr/bin/env python3
"""
Generate a map image showing the flight location with a plane in the center

This script creates a map visualization using OpenStreetMap tiles, centered on 
the flight's coordinates, with a plane icon positioned in the middle.

The script can generate:
- PNG images (using OpenStreetMap tiles + PIL/Pillow) - recommended
- SVG images (simplified map with geographic features) - fallback

Features:
- OpenStreetMap tile-based map rendering
- Plane icon matching index-maps.html design
- Optional flight information card overlay
- Rotates plane based on track/heading

Usage:
    # Generate PNG map with OpenStreetMap (requires: pip install pillow requests)
    python3 map_to_svg.py --lat 52.3667 --lon 13.5033
    
    # Generate PNG with track/heading
    python3 map_to_svg.py --lat 52.3667 --lon 13.5033 --track 264.2
    
    # Generate map with flight card overlay (requires: pip install cairosvg)
    python3 map_to_svg.py --lat 52.3667 --lon 13.5033 --track 264.2 \
        --overlay-card --callsign "DLH456" --origin "BER" --destination "CDG" \
        --origin-country "Germany" --destination-country "France" \
        --altitude 37375 --speed 451.4
    
    # Force SVG output (no external dependencies)
    python3 map_to_svg.py --lat 52.3667 --lon 13.5033 --format svg
    
    # Customize map size and zoom level
    python3 map_to_svg.py --lat 52.3667 --lon 13.5033 --zoom 12 --width 800 --height 480
    
    # See all options
    python3 map_to_svg.py --help

Dependencies:
    Required for PNG: pillow, requests
    Required for high-quality overlay: cairosvg + Cairo system library
        - macOS: brew install cairo
        - Linux: apt-get install libcairo2-dev (or equivalent)
        - Then: pip install cairosvg
    Fallback: PIL-based rendering (works without Cairo, but some detail is lost)
    
    See SETUP_SVG_RENDERING.md for detailed setup instructions.
"""

import argparse
import math
import os
import sys
import io

# Set up library path for Cairo on macOS (Homebrew)
# Monkey-patch ctypes.util.find_library to check Homebrew first
if sys.platform == 'darwin':
    homebrew_lib = '/opt/homebrew/lib'
    if os.path.exists(homebrew_lib):
        import ctypes.util
        original_find_library = ctypes.util.find_library
        
        def find_library_patched(name):
            """Patched find_library that checks Homebrew first for Cairo"""
            if 'cairo' in name.lower():
                # Check Homebrew first
                for lib_name in [f'lib{name}.2.dylib', f'{name}.2.dylib', f'lib{name}.dylib', f'{name}.dylib']:
                    path = os.path.join(homebrew_lib, lib_name)
                    if os.path.exists(path):
                        return path
                # Also try without version
                if name.startswith('cairo'):
                    for lib_name in ['libcairo.2.dylib', 'libcairo.dylib']:
                        path = os.path.join(homebrew_lib, lib_name)
                        if os.path.exists(path):
                            return path
            # Fall back to original
            return original_find_library(name)
        
        ctypes.util.find_library = find_library_patched

# Try to import image processing libraries
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Try to import SVG rendering library
try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    HAS_SVGLIB = True
except ImportError:
    HAS_SVGLIB = False

# Try to import cairosvg for SVG to PNG conversion
# On macOS with Homebrew, we need to help cairocffi find Cairo
# The issue is that cairocffi uses its own dlopen which doesn't check Homebrew paths
HAS_CAIROSVG = False
_cairosvg_module = None
try:
    if sys.platform == 'darwin':
        homebrew_lib = '/opt/homebrew/lib'
        cairo_lib = f'{homebrew_lib}/libcairo.2.dylib'
        if os.path.exists(cairo_lib):
            # Create a symlink in a standard location that cairocffi will find
            # Or patch cairocffi's source directly
            try:
                # Try to monkey-patch cairocffi's dlopen function
                # We need to do this before importing cairocffi
                import ctypes
                import ctypes.util
                
                # Patch find_library one more time with better logic
                original_find = ctypes.util.find_library
                def cairo_find_library(name):
                    if 'cairo' in name.lower() or name in ['cairo-2', 'cairo', 'libcairo-2']:
                        if os.path.exists(cairo_lib):
                            return cairo_lib
                    return original_find(name)
                ctypes.util.find_library = cairo_find_library
                
                # Also try to patch the dlopen in cairocffi after import
                # But first, let's try importing with the patched find_library
            except:
                pass
    
    import cairosvg
    _cairosvg_module = cairosvg
    # Test that it actually works with a proper SVG
    try:
        # Test with a valid SVG that has dimensions
        test_svg = b'<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
        cairosvg.svg2png(bytestring=test_svg)
        HAS_CAIROSVG = True
    except Exception as e:
        HAS_CAIROSVG = False
        # The library is installed but cairocffi can't find it, or there's another error
        # This might be a known issue on macOS with Homebrew
except (ImportError, OSError, AttributeError, Exception):
    HAS_CAIROSVG = False
    _cairosvg_module = None

# Try to import flight card generator
try:
    from generate_flight_card import (
        generate_flight_card_svg,
        format_altitude, format_speed, format_distance, format_track,
        format_vertical_rate, format_coordinates, get_country_flag
    )
    HAS_FLIGHT_CARD = True
except ImportError:
    HAS_FLIGHT_CARD = False
    format_altitude = format_speed = format_distance = format_track = None
    format_vertical_rate = format_coordinates = get_country_flag = None


def deg2num(lat_deg, lon_deg, zoom):
    """Convert lat/lon to tile numbers"""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)


def num2deg(xtile, ytile, zoom):
    """Convert tile numbers to lat/lon of top-left corner"""
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)


def get_osm_tile_url(xtile, ytile, zoom, tile_server='https://tile.openstreetmap.org'):
    """Get OpenStreetMap tile URL"""
    return f"{tile_server}/{zoom}/{xtile}/{ytile}.png"


def download_tile(url, timeout=5):
    """Download a map tile"""
    if not HAS_REQUESTS:
        return None
    try:
        response = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'FlightMapGenerator/1.0'
        })
        if response.status_code == 200:
            return response.content
    except Exception as e:
        print(f"Warning: Could not download tile: {e}", file=sys.stderr)
    return None


def create_inky_palette():
    """
    Create a color palette for Inky Impression 73 display
    The display supports: black, white, red, green, blue, yellow
    Returns a PIL Image palette
    """
    # Inky Impression 73 color palette (RGB values)
    # Colors: black, white, red, green, blue, yellow
    palette_colors = [
        (0, 0, 0),       # 0: Black
        (255, 255, 255), # 1: White
        (255, 0, 0),     # 2: Red
        (0, 255, 0),     # 3: Green
        (0, 0, 255),     # 4: Blue
        (255, 255, 0),   # 5: Yellow
    ]
    
    # Create a palette image (256 colors, but we only use 6)
    palette_image = Image.new('P', (1, 1))
    palette = []
    for r, g, b in palette_colors:
        palette.extend([r, g, b])
    # Fill remaining slots with black
    while len(palette) < 768:
        palette.extend([0, 0, 0])
    palette_image.putpalette(palette)
    return palette_image


def convert_to_inky_colors(image, dither=True):
    """
    Convert an image to Inky Impression 73 color palette
    
    Args:
        image: PIL Image (RGB mode)
        dither: Whether to use dithering for smoother color transitions
    
    Returns:
        PIL Image in RGB mode with only Inky-compatible colors
    """
    if not HAS_PIL:
        return image
    
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Create palette
    palette_image = create_inky_palette()
    
    # Quantize the image to the palette
    if dither:
        # Use Floyd-Steinberg dithering for better quality
        quantized = image.quantize(palette=palette_image, dither=Image.Dither.FLOYDSTEINBERG)
    else:
        # No dithering - faster but more color banding
        quantized = image.quantize(palette=palette_image, dither=Image.Dither.NONE)
    
    # Convert back to RGB for compatibility
    return quantized.convert('RGB')


def map_color_to_inky(color_rgb):
    """
    Map an RGB color to the nearest Inky Impression color
    
    Args:
        color_rgb: Tuple of (r, g, b) values (0-255)
    
    Returns:
        Tuple of (r, g, b) for nearest Inky color
    """
    r, g, b = color_rgb
    
    # Inky palette colors
    inky_colors = [
        (0, 0, 0),       # Black
        (255, 255, 255), # White
        (255, 0, 0),     # Red
        (0, 255, 0),     # Green
        (0, 0, 255),     # Blue
        (255, 255, 0),   # Yellow
    ]
    
    # Find closest color using Euclidean distance
    min_distance = float('inf')
    closest_color = inky_colors[0]
    
    for inky_r, inky_g, inky_b in inky_colors:
        distance = ((r - inky_r) ** 2 + (g - inky_g) ** 2 + (b - inky_b) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            closest_color = (inky_r, inky_g, inky_b)
    
    return closest_color


def generate_clear_skies_map(lat, lon, location_name, output_path='test_map.png', width=800, height=480, zoom=11, inky_mode=False):
    """
    Generate a "clear skies" map centered on a location (airport or city)
    
    Args:
        lat: Latitude of location to center on
        lon: Longitude of location to center on
        location_name: Name of location (airport code or city name)
        output_path: Output file path
        width: Map width in pixels
        height: Map height in pixels
        zoom: Zoom level (typically 10-12 for airports/cities)
        inky_mode: Whether to convert colors for Inky Impression display
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not HAS_PIL:
        return False
    
    if lat is None or lon is None:
        return False
    
    # Create flight data structure for map generation (without flight-specific data)
    clear_skies_data = {
        'lat': lat,
        'lon': lon,
        'callsign': 'CLEAR',
        'icao': 'CLEAR',
        'altitude': None,
        'speed': None,
        'track': None,
        'heading': None,
        'origin': None,
        'destination': None,
        'distance': None,
        'vertical_rate': None,
        'squawk': None,
        'location_name': location_name,
        'clear_skies': True  # Flag to indicate this is a clear skies map
    }
    
    # Generate map without flight card overlay, but with clear skies flag
    return generate_osm_map_png(clear_skies_data, output_path, width, height, zoom, overlay_card=False, inky_mode=inky_mode, clear_skies=True)


def generate_osm_map_png(flight_data, output_path='test_map.png', width=800, height=480, zoom=10, overlay_card=False, inky_mode=False, clear_skies=False):
    """
    Generate a PNG map using OpenStreetMap tiles
    
    Args:
        flight_data: Dictionary with flight information (lat, lon, track, heading)
        output_path: Output file path
        width: Map width in pixels
        height: Map height in pixels
        zoom: Zoom level (typically 1-18)
        overlay_card: Whether to overlay the flight card
        inky_mode: Whether to convert colors for Inky Impression display
        clear_skies: Whether this is a "clear skies" map (no flight, just location)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not HAS_PIL:
        return False
    
    lat = flight_data.get('lat')
    lon = flight_data.get('lon')
    
    if lat is None or lon is None:
        return False
    
    # Calculate which tile contains our coordinates
    center_xtile, center_ytile = deg2num(lat, lon, zoom)
    
    # Calculate target plane position first (before calculating tile requirements)
    # This affects how many tiles we need, since the crop might be shifted
    temp_card_x = None
    if overlay_card and HAS_FLIGHT_CARD:
        try:
            temp_card_w = 400  # Default card width
            temp_padding = 20
            temp_card_x = width - temp_card_w - temp_padding
        except:
            pass
    
    if temp_card_x is not None:
        target_plane_x = temp_card_x // 2
    else:
        target_plane_x = width // 2
    target_plane_y = height // 2
    
    # Calculate how many tiles we need to cover the area
    # OSM tiles are 256x256 pixels
    # We need extra tiles to account for the shifted crop position
    # The crop will be shifted by (width/2 - target_plane_x) pixels
    # Add extra margin to ensure we never need padding
    tile_size = 256
    crop_shift_x = (width // 2) - target_plane_x  # How much we're shifting left/right (can be negative)
    # Calculate required width: base width + shift amount + margin on both sides
    required_width = width + abs(crop_shift_x) + (tile_size * 2)  # Extra margin
    required_height = height + (tile_size * 2)  # Extra margin
    tiles_x = math.ceil(required_width / tile_size)
    tiles_y = math.ceil(required_height / tile_size)
    
    # Calculate tile range (centered around the tile containing our coordinates)
    start_xtile = center_xtile - tiles_x // 2
    start_ytile = center_ytile - tiles_y // 2
    end_xtile = start_xtile + tiles_x
    end_ytile = start_ytile + tiles_y
    
    # Get the lat/lon of the top-left corner of the start tile
    start_tile_lat, start_tile_lon = num2deg(start_xtile, start_ytile, zoom)
    
    # Calculate pixels per degree using Web Mercator projection
    n = 2.0 ** zoom
    # Longitude: uniform scaling
    pixels_per_deg_lon = (tile_size * n) / 360.0
    # Latitude: Web Mercator formula (varies with latitude)
    lat1_rad = math.radians(start_tile_lat)
    lat2_rad = math.radians(start_tile_lat + 1)
    # Calculate actual pixel distance for 1 degree at this latitude
    y1 = (1 - math.log(math.tan(lat1_rad) + (1 / math.cos(lat1_rad))) / math.pi) / 2 * n * tile_size
    y2 = (1 - math.log(math.tan(lat2_rad) + (1 / math.cos(lat2_rad))) / math.pi) / 2 * n * tile_size
    pixels_per_deg_lat = abs(y2 - y1)
    
    # Calculate pixel position of our coordinates within the tile grid
    # First convert our lat/lon to pixel coordinates in the full map
    lon_pixel = (lon + 180) / 360 * (tile_size * n)
    lat_rad = math.radians(lat)
    lat_pixel = (1 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2 * (tile_size * n)
    
    # Calculate pixel position of start tile
    start_lon_pixel = (start_tile_lon + 180) / 360 * (tile_size * n)
    start_lat_rad = math.radians(start_tile_lat)
    start_lat_pixel = (1 - math.log(math.tan(start_lat_rad) + (1 / math.cos(start_lat_rad))) / math.pi) / 2 * (tile_size * n)
    
    # Calculate offset within our tile grid
    offset_x = lon_pixel - start_lon_pixel
    offset_y = lat_pixel - start_lat_pixel
    
    # Calculate total dimensions of tile grid
    total_width = tiles_x * tile_size
    total_height = tiles_y * tile_size
    
    # Create a blank image to composite tiles
    # Use white background for Inky mode, light blue for normal mode
    if inky_mode:
        background_color = '#FFFFFF'  # White for e-ink
    else:
        background_color = '#e8f4f8'  # Light blue for normal
    map_image = Image.new('RGB', (total_width, total_height), color=background_color)
    
    # Download and paste tiles
    print(f"Downloading {tiles_x * tiles_y} map tiles...", file=sys.stderr)
    downloaded = 0
    for y in range(start_ytile, end_ytile):
        for x in range(start_xtile, end_xtile):
            # Handle tile wrapping (OSM tiles wrap at boundaries)
            tile_x = x % (2 ** zoom)
            tile_url = get_osm_tile_url(tile_x, y, zoom)
            tile_data = download_tile(tile_url)
            
            if tile_data:
                try:
                    tile_img = Image.open(io.BytesIO(tile_data))
                    paste_x = (x - start_xtile) * tile_size
                    paste_y = (y - start_ytile) * tile_size
                    map_image.paste(tile_img, (paste_x, paste_y))
                    downloaded += 1
                except Exception as e:
                    print(f"Warning: Could not process tile {x},{y}: {e}", file=sys.stderr)
    
    if downloaded == 0:
        print("Error: Could not download any map tiles", file=sys.stderr)
        return False
    
    print(f"Downloaded {downloaded} tiles", file=sys.stderr)
    
    # target_plane_x and target_plane_y were already calculated above before tile calculation
    
    # Crop to desired size, positioning the flight location at the target plane position
    # Our coordinates are at offset_x, offset_y within the tile grid
    # We want the crop so that (offset_x, offset_y) maps to (target_plane_x, target_plane_y) in the final image
    center_x = offset_x
    center_y = offset_y
    
    left = int(center_x - target_plane_x)
    top = int(center_y - target_plane_y)
    right = left + width
    bottom = top + height
    
    # Clip crop bounds to available tile area (we should have enough tiles, but be safe)
    # Ensure we never add padding - if bounds are outside, adjust the crop intelligently
    if left < 0:
        # Shift right to compensate
        right = right - left
        left = 0
    if top < 0:
        # Shift down to compensate
        bottom = bottom - top
        top = 0
    if right > total_width:
        # Shift left to fit (we should have enough tiles, but adjust if needed)
        excess = right - total_width
        if left >= excess:
            left = left - excess
            right = total_width
        else:
            # We don't have enough tiles - this shouldn't happen with our margin calculation
            # But if it does, crop what we have and resize (no padding)
            right = total_width
            if left >= right:
                left = max(0, right - width)
    if bottom > total_height:
        # Shift up to fit
        excess = bottom - total_height
        if top >= excess:
            top = top - excess
            bottom = total_height
        else:
            bottom = total_height
            if top >= bottom:
                top = max(0, bottom - height)
    
    # Crop the image (no padding - we ensure we have enough tiles)
    if left < right and top < bottom:
        cropped_image = map_image.crop((left, top, right, bottom))
        # If crop is smaller than desired, resize (preserves map content, no white padding)
        if cropped_image.size != (width, height):
            cropped_image = cropped_image.resize((width, height), Image.Resampling.LANCZOS)
    else:
        # Fallback: this shouldn't happen, but create from tiles if it does
        cropped_image = map_image.resize((width, height), Image.Resampling.LANCZOS)
    
    # Note: target_plane_x and target_plane_y were already calculated above before cropping
    # We'll reuse those values here for positioning the plane icon
    
    # Calculate flight card position (if overlay is requested) for card overlay later
    card_x = None
    card_w = None
    card_svg_precomputed = None
    if overlay_card and HAS_FLIGHT_CARD:
        try:
            # Generate flight card to get its dimensions (we'll reuse this SVG later)
            # Only precompute if not in inky_mode (colors might change)
            if not inky_mode:
                card_svg_precomputed = generate_flight_card_svg(flight_data, output_path=None, inky_mode=False)
            
            # Flight card width is typically 400px (defined in generate_flight_card.py)
            card_w = 400  # Default card width
            padding = 20
            card_x = width - card_w - padding
        except:
            pass
    
    # Calculate rotation (same as index-maps.html: angle directly)
    # Heading is preferred, track is fallback
    # Skip plane rendering for clear skies maps
    track = flight_data.get('track')
    heading = flight_data.get('heading')
    rotation_angle = 0
    if not clear_skies:
        if heading is not None:
            rotation_angle = heading
        elif track is not None:
            rotation_angle = track
    
    # The exact SVG plane path from index-maps.html (Material Design plane icon):
    # viewBox="0 0 24 24"
    # path: "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"
    # The icon points to the right (east) by default in SVG coordinates
    # Skip plane icon creation for clear skies maps
    plane_icon = None
    plane_size = 40  # Icon size in pixels (matching index-maps.html which uses 40x40)
    
    if not clear_skies:
        # Choose plane color based on inky_mode
        if inky_mode:
            plane_color = "#0000FF"  # Blue for Inky
            plane_stroke = "#000000"  # Black stroke for contrast
            shadow_filter = ""  # No shadow on e-ink displays
        else:
            plane_color = "#667eea"  # Original purple-blue
            plane_stroke = "white"
            shadow_filter = 'filter="url(#planeShadow)"'
        
        # Create SVG string with the plane icon, rotated
        plane_svg = f'''<svg width="{plane_size}" height="{plane_size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="planeShadow">
                    <feGaussianBlur in="SourceAlpha" stdDeviation="1"/>
                    <feOffset dx="2" dy="2" result="offsetblur"/>
                    <feComponentTransfer>
                        <feFuncA type="linear" slope="0.4"/>
                    </feComponentTransfer>
                    <feMerge>
                        <feMergeNode/>
                        <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                </filter>
            </defs>
            <g transform="rotate({rotation_angle} 12 12)">
                <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" 
                      fill="{plane_color}" stroke="{plane_stroke}" stroke-width="1" {shadow_filter}/>
            </g>
        </svg>'''
        
        # Try to render SVG using cairosvg first (best quality), then svglib
        plane_icon = None
        
        # Method 1: Try cairosvg (best quality, preserves SVG exactly)
        if HAS_CAIROSVG and _cairosvg_module:
            try:
                png_data = _cairosvg_module.svg2png(bytestring=plane_svg.encode('utf-8'), output_width=plane_size, output_height=plane_size)
                plane_icon = Image.open(io.BytesIO(png_data))
            except Exception as e:
                # Fall through to next method
                pass
        
        # Method 2: Try svglib if cairosvg failed
        if plane_icon is None and HAS_SVGLIB:
            try:
                # Render SVG to PIL Image
                drawing = svg2rlg(io.BytesIO(plane_svg.encode('utf-8')))
                if drawing:
                    # Render to PNG bytes at higher DPI for better quality
                    png_data = renderPM.drawToString(drawing, fmt='PNG', dpi=144)  # Higher DPI for better quality
                    plane_icon = Image.open(io.BytesIO(png_data))
                    # Resize to exact size if needed
                    if plane_icon.size != (plane_size, plane_size):
                        plane_icon = plane_icon.resize((plane_size, plane_size), Image.Resampling.LANCZOS)
            except Exception as e:
                print(f"Warning: Could not render plane SVG with svglib: {e}", file=sys.stderr)
        
            # Fallback: Draw polygon approximation if SVG rendering failed
            if plane_icon is None:
                # Create polygon approximation of the plane icon
                scale = plane_size / 24.0
                svg_points = [
                    (21, 16), (21, 14), (13, 9), (13, 3.5), (11.5, 3), (10, 3.5),
                    (10, 9), (2, 14), (2, 16), (10, 13.5), (10, 19), (8, 20.5),
                    (8, 22), (11.5, 21), (12.5, 21.5), (15, 21), (15, 20.5),
                    (13, 19), (13, 13.5), (21, 16)
                ]
                
                base_points = [((sx - 12) * scale, (sy - 12) * scale) for sx, sy in svg_points]
                
                angle_rad = math.radians(rotation_angle)
                rotated_points = []
                for px, py in base_points:
                    rot_angle = angle_rad - math.pi / 2
                    rotated_x = px * math.cos(rot_angle) - py * math.sin(rot_angle)
                    rotated_y = px * math.sin(rot_angle) + py * math.cos(rot_angle)
                    rotated_points.append((plane_size/2 + rotated_x, plane_size/2 + rotated_y))
                
                # Create plane icon image
                plane_icon = Image.new('RGBA', (plane_size, plane_size), (0, 0, 0, 0))
                plane_draw = ImageDraw.Draw(plane_icon)
                
                # Draw shadow (skip in inky_mode for cleaner look on e-ink)
                if not inky_mode:
                    shadow_points = [(x + 2, y + 2) for x, y in rotated_points]
                    plane_draw.polygon(shadow_points, fill=(0, 0, 0, 102))
                
                # Draw plane - use Inky-compatible color if in inky_mode
                if inky_mode:
                    plane_fill = (0, 0, 255)  # Blue
                    plane_outline = (0, 0, 0)  # Black
                else:
                    plane_fill = (102, 126, 234, 255)  # Original purple-blue
                    plane_outline = (255, 255, 255, 255)  # White
                plane_draw.polygon(rotated_points, fill=plane_fill, outline=plane_outline)
    
    # Composite plane icon onto map at the target position (skip for clear skies)
    if not clear_skies:
        img_rgba = cropped_image.convert('RGBA')
        paste_x = int(target_plane_x - plane_size // 2)
        paste_y = int(target_plane_y - plane_size // 2)
        img_rgba.paste(plane_icon, (paste_x, paste_y), plane_icon)
        cropped_image = img_rgba.convert('RGB')
    
    # Add "Skies are clear!" text overlay if this is a clear skies map
    if clear_skies:
        try:
            from PIL import ImageFont, ImageDraw
            
            # Convert to RGBA for text overlay
            img_rgba = cropped_image.convert('RGBA')
            draw = ImageDraw.Draw(img_rgba)
            
            # Get location name for display
            location_name = flight_data.get('location_name', 'Location')
            
            # Try to load a nice font (system default if not available)
            try:
                if sys.platform == 'darwin':
                    font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
                    font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
                else:
                    font_large = ImageFont.load_default()
                    font_small = ImageFont.load_default()
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Draw semi-transparent background for text
            text_bg_height = 120
            text_bg_y = (height - text_bg_height) // 2
            overlay_bg = Image.new('RGBA', (width, text_bg_height), (255, 255, 255, 200))
            img_rgba.paste(overlay_bg, (0, text_bg_y), overlay_bg)
            
            # Draw "Skies are clear!" text
            text_main = "Skies are clear!"
            if inky_mode:
                text_color = (0, 0, 0)  # Black for Inky
            else:
                text_color = (31, 41, 55)  # Dark gray
            
            # Center the text
            bbox = draw.textbbox((0, 0), text_main, font=font_large)
            text_width = bbox[2] - bbox[0]
            text_x = (width - text_width) // 2
            text_y = text_bg_y + 20
            
            draw.text((text_x, text_y), text_main, fill=text_color, font=font_large)
            
            # Draw location name below
            location_text = f"📍 {location_name}"
            bbox_location = draw.textbbox((0, 0), location_text, font=font_small)
            location_width = bbox_location[2] - bbox_location[0]
            location_x = (width - location_width) // 2
            location_y = text_y + 60
            
            draw.text((location_x, location_y), location_text, fill=text_color, font=font_small)
            
            # Convert back to RGB
            cropped_image = img_rgba.convert('RGB')
        except Exception as e:
            print(f"Warning: Could not add clear skies text overlay: {e}", file=sys.stderr)
    
    # Overlay flight card if requested (skip for clear skies maps)
    if overlay_card and HAS_FLIGHT_CARD and not clear_skies:
        try:
            # Generate flight card SVG (this has all the quality and detail)
            # Reuse the precomputed SVG if we generated it earlier for plane positioning
            # But regenerate if inky_mode changed the colors
            if card_svg_precomputed is not None and not inky_mode:
                card_svg = card_svg_precomputed
            else:
                card_svg = generate_flight_card_svg(flight_data, output_path=None, inky_mode=inky_mode)
            print(f"Generated flight card SVG ({len(card_svg)} characters)", file=sys.stderr)
            
            # Try to render SVG to PNG (preserves all quality and styling)
            card_image = None
            
            # Method 1: Try cairosvg (best quality, requires system library)
            if HAS_CAIROSVG and _cairosvg_module:
                try:
                    card_png_data = _cairosvg_module.svg2png(bytestring=card_svg.encode('utf-8'), output_width=400)
                    card_image = Image.open(io.BytesIO(card_png_data))
                    print("Flight card rendered using cairosvg (best quality)", file=sys.stderr)
                except Exception as e:
                    print(f"Warning: cairosvg rendering failed: {e}", file=sys.stderr)
            
            # Method 2: Try svglib (good quality, but requires Cairo for reportlab)
            if not card_image and HAS_SVGLIB:
                try:
                    print("Attempting to render flight card using svglib...", file=sys.stderr)
                    drawing = svg2rlg(io.BytesIO(card_svg.encode('utf-8')))
                    if drawing:
                        # Render at high DPI for better quality
                        card_png_data = renderPM.drawToString(drawing, fmt='PNG', dpi=150)
                        card_image = Image.open(io.BytesIO(card_png_data))
                        print("Flight card rendered using svglib (good quality)", file=sys.stderr)
                except Exception as e:
                    error_msg = str(e)
                    if 'rlPyCairo' in error_msg or 'Cairo' in error_msg or 'renderPM backend' in error_msg:
                        print("Note: svglib requires Cairo system library for PNG rendering.", file=sys.stderr)
                        print("  Install with: brew install cairo (macOS) or apt-get install libcairo2-dev (Linux)", file=sys.stderr)
                    else:
                        print(f"Warning: svglib rendering failed: {e}", file=sys.stderr)
            
            # Method 3: Fallback to PIL-based rendering (simpler but less detailed)
            if not card_image:
                print("Falling back to PIL-based rendering (some detail may be lost)...", file=sys.stderr)
                try:
                    card_image = render_flight_card_pil(flight_data, inky_mode=inky_mode)
                    if card_image:
                        print("Flight card rendered using PIL (basic quality)", file=sys.stderr)
                except Exception as e:
                    print(f"Warning: PIL rendering failed: {e}", file=sys.stderr)
            
            # Overlay the card on the map
            if card_image:
                # Position card in bottom-right corner with padding
                # Use the card_w and card_x we calculated earlier for plane positioning
                if card_w is None:
                    card_w, card_h = card_image.size
                    padding = 20
                    card_x = width - card_w - padding
                else:
                    card_h = card_image.size[1]
                    # card_x was already calculated above for plane positioning
                card_y = height - card_h - padding
                
                # Convert card to RGBA if needed
                if card_image.mode != 'RGBA':
                    card_image = card_image.convert('RGBA')
                
                # Composite card onto map
                img_rgba = cropped_image.convert('RGBA')
                img_rgba.paste(card_image, (int(card_x), int(card_y)), card_image)
                cropped_image = img_rgba.convert('RGB')
                print("Flight card overlayed on map", file=sys.stderr)
            else:
                # Save SVG to file as last resort
                temp_svg_file = output_path.replace('.png', '_card.svg')
                try:
                    with open(temp_svg_file, 'w', encoding='utf-8') as f:
                        f.write(card_svg)
                    print(f"Warning: Could not render flight card to PNG.", file=sys.stderr)
                    print(f"  Flight card SVG saved to: {temp_svg_file}", file=sys.stderr)
                    print(f"  Install svglib for better quality: pip install svglib reportlab", file=sys.stderr)
                except Exception as e2:
                    print(f"Warning: Could not save flight card SVG: {e2}", file=sys.stderr)
                
                print("", file=sys.stderr)
                print("To get high-quality SVG rendering with all details preserved:", file=sys.stderr)
                print("  1. Install Cairo system library:", file=sys.stderr)
                print("     macOS: brew install cairo", file=sys.stderr)
                print("     Linux: apt-get install libcairo2-dev  (or equivalent)", file=sys.stderr)
                print("  2. Then reinstall cairosvg: pip install --upgrade cairosvg", file=sys.stderr)
                print("", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not overlay flight card: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    
    # Convert to Inky colors if requested
    if inky_mode:
        print("Converting image to Inky Impression 73 color palette...", file=sys.stderr)
        cropped_image = convert_to_inky_colors(cropped_image, dither=True)
    
    # Save the image
    cropped_image.save(output_path, 'PNG')
    return True


def render_flight_card_pil(flight_data, card_width=400, inky_mode=False):
    """
    Render flight card directly using PIL/Pillow (no SVG rendering needed)
    
    Args:
        flight_data: Dictionary with flight information
        card_width: Width of the card in pixels
        inky_mode: Whether to use Inky Impression 73 compatible colors
    
    Returns:
        PIL.Image: Rendered flight card image
    """
    if not HAS_PIL or not HAS_FLIGHT_CARD:
        return None
    
    # Card dimensions
    base_card_height = 276
    corner_radius = 12
    header_height = 70
    
    # Colors - use Inky-compatible colors if inky_mode is enabled
    if inky_mode:
        # Inky Impression 73 palette: black, white, red, green, blue, yellow
        header_color_start = (0, 0, 255)   # Blue
        header_color_end = (0, 0, 255)     # Blue (solid, no gradient)
        airport_code_color = (0, 0, 255)   # Blue
        label_color = (0, 0, 0)            # Black
        country_color = (0, 0, 0)          # Black
        footer_color_start = (255, 255, 255)  # White
        footer_color_end = (255, 255, 255)    # White (solid)
        text_color_dark = (0, 0, 0)        # Black
    else:
        # Original colors
        header_color_start = (102, 126, 234)  # #667eea
        header_color_end = (118, 75, 162)     # #764ba2
        airport_code_color = (102, 126, 234)  # #667eea
        label_color = (0, 0, 0)               # #000000 - Changed from light gray to black
        country_color = (0, 0, 0)             # #000000 - Changed from gray to black
        footer_color_start = (243, 244, 246)  # #f3f4f6
        footer_color_end = (229, 231, 235)    # #e5e7eb
        text_color_dark = (31, 41, 55)        # #1f2937
    
    # Extract flight data
    callsign = flight_data.get('callsign', 'N/A')
    icao = flight_data.get('icao', 'TEST01')
    origin = flight_data.get('origin', '---')
    destination = flight_data.get('destination', '---')
    origin_country = flight_data.get('origin_country', '')
    destination_country = flight_data.get('destination_country', '')
    altitude = flight_data.get('altitude', 0)
    speed = flight_data.get('speed', 0)
    track = flight_data.get('track', None)
    vertical_rate = flight_data.get('vertical_rate', None)
    distance = flight_data.get('distance', None)
    squawk = flight_data.get('squawk', None)
    lat = flight_data.get('lat', None)
    lon = flight_data.get('lon', None)
    aircraft_model = flight_data.get('aircraft_model', None)
    aircraft_type = flight_data.get('aircraft_type', None)
    aircraft_registration = flight_data.get('aircraft_registration', None)
    
    # Calculate footer items
    footer_items = []
    footer_items.append(('Altitude', format_altitude(altitude)))
    footer_items.append(('Speed', format_speed(speed)))
    footer_items.append(('Track', format_track(track)))
    footer_items.append(('Vertical', format_vertical_rate(vertical_rate) if vertical_rate is not None else 'N/A'))
    footer_items.append(('Distance', format_distance(distance) if distance is not None else 'N/A'))
    footer_items.append(('Squawk', squawk if squawk else 'N/A'))
    
    # Calculate card height
    items_per_row = 3
    footer_row_height = 40
    num_grid_rows = (len(footer_items) + items_per_row - 1) // items_per_row
    full_width_items = 2  # Location and Aircraft
    footer_height = 16 + (num_grid_rows * footer_row_height) + (full_width_items * footer_row_height)
    card_height = base_card_height + max(0, footer_height - 66)
    
    # Create image with white background
    img = Image.new('RGBA', (card_width, card_height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle background
    draw.rectangle([0, 0, card_width-1, card_height-1], fill=(255, 255, 255, 255), outline=None)
    
    # Draw header with gradient
    header_gradient = Image.new('RGB', (card_width, header_height))
    header_draw = ImageDraw.Draw(header_gradient)
    for i in range(header_height):
        ratio = i / header_height
        r = int(header_color_start[0] * (1 - ratio) + header_color_end[0] * ratio)
        g = int(header_color_start[1] * (1 - ratio) + header_color_end[1] * ratio)
        b = int(header_color_start[2] * (1 - ratio) + header_color_end[2] * ratio)
        header_draw.rectangle([0, i, card_width, i+1], fill=(r, g, b))
    
    img.paste(header_gradient, (0, 0))
    
    # Draw header text
    try:
        callsign_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26) if sys.platform == 'darwin' else ImageFont.load_default()
        icao_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14) if sys.platform == 'darwin' else ImageFont.load_default()
    except:
        callsign_font = ImageFont.load_default()
        icao_font = ImageFont.load_default()
    
    header_center_y = header_height / 2
    callsign_y = header_center_y - 10
    icao_y = callsign_y + 18
    
    draw.text((20, callsign_y), str(callsign), fill=(255, 255, 255, 255), font=callsign_font)
    draw.text((20, icao_y), str(icao), fill=(255, 255, 255, 200), font=icao_font)
    
    # Route section
    route_section_y = header_height
    route_section_height = 140
    route_content_top = route_section_y + 24
    route_content_bottom = route_section_y + route_section_height - 24
    route_center_y = (route_content_top + route_content_bottom) / 2
    
    airport_code_y = route_center_y + 8
    label_y = airport_code_y - 28 - 8 - 4
    country_y = airport_code_y + 12 + 4 + 5
    
    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11) if sys.platform == 'darwin' else ImageFont.load_default()
        airport_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40) if sys.platform == 'darwin' else ImageFont.load_default()
        country_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14) if sys.platform == 'darwin' else ImageFont.load_default()
    except:
        label_font = ImageFont.load_default()
        airport_font = ImageFont.load_default()
        country_font = ImageFont.load_default()
    
    draw.text((20, label_y), "FROM", fill=label_color, font=label_font)
    draw.text((20, airport_code_y - 30), str(origin), fill=airport_code_color, font=airport_font)
    if origin_country:
        flag = get_country_flag(origin_country)
        # PIL may not render emoji flags properly, so we'll just use the country name
        # The SVG version will have the flags with proper font families
        draw.text((20, country_y), origin_country, fill=country_color, font=country_font)
    
    # Draw destination
    dest_bbox = draw.textbbox((0, 0), str(destination), font=airport_font)
    dest_width = dest_bbox[2] - dest_bbox[0]
    draw.text((card_width - 20 - dest_width, label_y), "TO", fill=label_color, font=label_font)
    draw.text((card_width - 20 - dest_width, airport_code_y - 30), str(destination), fill=airport_code_color, font=airport_font)
    if destination_country:
        flag = get_country_flag(destination_country)
        # PIL may not render emoji flags properly, so we'll just use the country name
        # The SVG version will have the flags with proper font families
        country_text = destination_country
        country_bbox = draw.textbbox((0, 0), country_text, font=country_font)
        country_width = country_bbox[2] - country_bbox[0]
        draw.text((card_width - 20 - country_width, country_y), country_text, fill=country_color, font=country_font)
    
    # Draw plane icon in center
    plane_center_x = card_width / 2
    plane_center_y = route_center_y
    plane_size = 24
    plane_points = [
        (plane_center_x + plane_size, plane_center_y),
        (plane_center_x - plane_size//2, plane_center_y - plane_size//2),
        (plane_center_x - plane_size//4, plane_center_y),
        (plane_center_x - plane_size//2, plane_center_y + plane_size//2),
    ]
    draw.polygon(plane_points, fill=airport_code_color, outline=(255, 255, 255, 255))
    
    # Draw footer
    footer_start_y = header_height + route_section_height
    footer_gradient = Image.new('RGB', (card_width, card_height - footer_start_y))
    footer_draw = ImageDraw.Draw(footer_gradient)
    footer_height_px = card_height - footer_start_y
    for i in range(footer_height_px):
        ratio = i / footer_height_px if footer_height_px > 0 else 0
        r = int(footer_color_start[0] * (1 - ratio) + footer_color_end[0] * ratio)
        g = int(footer_color_start[1] * (1 - ratio) + footer_color_end[1] * ratio)
        b = int(footer_color_start[2] * (1 - ratio) + footer_color_end[2] * ratio)
        footer_draw.rectangle([0, i, card_width, i+1], fill=(r, g, b))
    img.paste(footer_gradient, (0, footer_start_y))
    
    # Draw border line at top of footer
    draw.line([(0, footer_start_y), (card_width, footer_start_y)], fill=(229, 231, 235, 255), width=1)
    
    # Draw footer items
    item_width = (card_width - 40 - (items_per_row - 1) * 16) / items_per_row
    footer_start_y_content = footer_start_y + 21
    
    try:
        footer_label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11) if sys.platform == 'darwin' else ImageFont.load_default()
        footer_value_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16) if sys.platform == 'darwin' else ImageFont.load_default()
        footer_mono_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14) if sys.platform == 'darwin' else ImageFont.load_default()
    except:
        footer_label_font = ImageFont.load_default()
        footer_value_font = ImageFont.load_default()
        footer_mono_font = ImageFont.load_default()
    
    for i, (label, value) in enumerate(footer_items):
        row = i // items_per_row
        col = i % items_per_row
        x = 20 + col * (item_width + 16)
        y = footer_start_y_content + row * footer_row_height
        
        draw.text((x, y), label.upper(), fill=label_color, font=footer_label_font)
        value_font = footer_mono_font if label == 'Squawk' else footer_value_font
        draw.text((x, y + 20), value, fill=text_color_dark, font=value_font)
    
    # Location (full width)
    coord_y = footer_start_y_content + num_grid_rows * footer_row_height
    location_value = format_coordinates(lat, lon) if lat is not None and lon is not None else 'N/A'
    draw.text((20, coord_y), "LOCATION", fill=label_color, font=footer_label_font)
    draw.text((20, coord_y + 20), location_value, fill=text_color_dark, font=footer_mono_font)
    
    # Aircraft info (full width)
    aircraft_y = footer_start_y_content + num_grid_rows * footer_row_height + footer_row_height
    aircraft_text = aircraft_model or aircraft_type or 'N/A'
    if aircraft_registration:
        aircraft_text += f" ({aircraft_registration})"
    draw.text((20, aircraft_y), "AIRCRAFT", fill=label_color, font=footer_label_font)
    draw.text((20, aircraft_y + 20), aircraft_text, fill=text_color_dark, font=footer_value_font)
    
    return img


def generate_map_svg(flight_data, output_path='test_map.svg', width=800, height=480, zoom=10):
    """
    Generate an SVG map section with plane in the center
    
    Args:
        flight_data: Dictionary with flight information (lat, lon, callsign, etc.)
        output_path: Output file path
        width: Map width in pixels
        height: Map height in pixels
        zoom: Zoom level (higher = more zoomed in)
    
    Returns:
        str: SVG content
    """
    lat = flight_data.get('lat')
    lon = flight_data.get('lon')
    callsign = flight_data.get('callsign', 'N/A')
    altitude = flight_data.get('altitude', 0)
    speed = flight_data.get('speed', 0)
    
    if lat is None or lon is None:
        raise ValueError("Latitude and longitude are required")
    
    # Map styling - more realistic map colors
    map_bg_color = '#f5f5f0'  # Light beige/cream background
    water_color = '#b8d4e8'  # Light blue for water
    road_major_color = '#666666'  # Gray for major roads
    road_minor_color = '#999999'  # Lighter gray for minor roads
    building_color = '#d0d0d0'  # Light gray for buildings
    park_color = '#c8e6c9'  # Light green for parks
    text_color = '#333333'
    plane_color = '#667eea'
    
    # Calculate center coordinates (use provided lat/lon)
    center_lat = lat
    center_lon = lon
    
    # Generate map features - roads, buildings, geographic features
    # Create a realistic map layout with roads, buildings, parks, etc.
    
    svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <!-- Plane icon gradient -->
        <linearGradient id="planeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:{plane_color};stop-opacity:1" />
            <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
        </linearGradient>
        
        <!-- Shadow filter for plane -->
        <filter id="planeShadow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="3"/>
            <feOffset dx="2" dy="2" result="offsetblur"/>
            <feComponentTransfer>
                <feFuncA type="linear" slope="0.3"/>
            </feComponentTransfer>
            <feMerge>
                <feMergeNode/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>
        </filter>
    </defs>
    
    <!-- Map background -->
    <rect width="{width}" height="{height}" fill="{map_bg_color}"/>
    
    <!-- Water bodies / rivers -->
    <ellipse cx="{width*0.3}" cy="{height*0.7}" rx="{width*0.15}" ry="{height*0.1}" fill="{water_color}" opacity="0.6"/>
    <ellipse cx="{width*0.7}" cy="{height*0.3}" rx="{width*0.12}" ry="{height*0.08}" fill="{water_color}" opacity="0.5"/>
    
    <!-- Parks / green spaces -->
    <ellipse cx="{width*0.2}" cy="{height*0.3}" rx="{width*0.12}" ry="{height*0.15}" fill="{park_color}" opacity="0.7"/>
    <rect x="{width*0.65}" y="{height*0.6}" width="{width*0.2}" height="{height*0.25}" rx="20" fill="{park_color}" opacity="0.7"/>
    
    <!-- Major roads (highways) - diagonal and grid -->
    <g stroke="{road_major_color}" stroke-width="4" fill="none" opacity="0.8">
        <!-- Horizontal major road -->
        <line x1="0" y1="{height*0.4}" x2="{width}" y2="{height*0.4}"/>
        <line x1="0" y1="{height*0.6}" x2="{width}" y2="{height*0.6}"/>
        <!-- Vertical major roads -->
        <line x1="{width*0.3}" y1="0" x2="{width*0.3}" y2="{height}"/>
        <line x1="{width*0.7}" y1="0" x2="{width*0.7}" y2="{height}"/>
        <!-- Diagonal road -->
        <line x1="0" y1="{height*0.2}" x2="{width*0.8}" y2="{height}"/>
    </g>
    
    <!-- Minor roads / streets -->
    <g stroke="{road_minor_color}" stroke-width="2" fill="none" opacity="0.6">
        <!-- Grid of minor roads -->
        <line x1="0" y1="{height*0.25}" x2="{width}" y2="{height*0.25}"/>
        <line x1="0" y1="{height*0.5}" x2="{width}" y2="{height*0.5}"/>
        <line x1="0" y1="{height*0.75}" x2="{width}" y2="{height*0.75}"/>
        <line x1="{width*0.15}" y1="0" x2="{width*0.15}" y2="{height}"/>
        <line x1="{width*0.5}" y1="0" x2="{width*0.5}" y2="{height}"/>
        <line x1="{width*0.85}" y1="0" x2="{width*0.85}" y2="{height}"/>
    </g>
    
    <!-- Buildings / city blocks -->
    <g fill="{building_color}" opacity="0.7">
        <!-- Various building shapes -->
        <rect x="{width*0.1}" y="{height*0.1}" width="{width*0.08}" height="{height*0.12}" rx="2"/>
        <rect x="{width*0.25}" y="{height*0.15}" width="{width*0.06}" height="{height*0.18}" rx="2"/>
        <rect x="{width*0.4}" y="{height*0.05}" width="{width*0.1}" height="{height*0.25}" rx="2"/>
        <rect x="{width*0.55}" y="{height*0.12}" width="{width*0.09}" height="{height*0.15}" rx="2"/>
        <rect x="{width*0.7}" y="{height*0.08}" width="{width*0.07}" height="{height*0.2}" rx="2"/>
        <rect x="{width*0.82}" y="{height*0.15}" width="{width*0.08}" height="{height*0.12}" rx="2"/>
        
        <!-- Buildings in lower area -->
        <rect x="{width*0.12}" y="{height*0.65}" width="{width*0.07}" height="{height*0.15}" rx="2"/>
        <rect x="{width*0.35}" y="{height*0.68}" width="{width*0.09}" height="{height*0.18}" rx="2"/>
        <rect x="{width*0.52}" y="{height*0.7}" width="{width*0.08}" height="{height*0.12}" rx="2"/>
        <rect x="{width*0.68}" y="{height*0.65}" width="{width*0.1}" height="{height*0.2}" rx="2"/>
    </g>
    
    <!-- Road center lines (yellow) -->
    <g stroke="#ffd700" stroke-width="1" stroke-dasharray="8,4" opacity="0.6">
        <line x1="0" y1="{height*0.4}" x2="{width}" y2="{height*0.4}"/>
        <line x1="0" y1="{height*0.6}" x2="{width}" y2="{height*0.6}"/>
        <line x1="{width*0.3}" y1="0" x2="{width*0.3}" y2="{height}"/>
        <line x1="{width*0.7}" y1="0" x2="{width*0.7}" y2="{height}"/>
    </g>
    
    <!-- Plane icon in center -->
    '''
    
    # Calculate plane rotation if track/heading is available
    # On maps: 0° = North, 90° = East, 180° = South, 270° = West
    # In SVG: 0° = right (East), 90° = down (South), 180° = left (West), 270° = up (North)
    # So we need to convert: SVG_angle = map_angle - 90
    track = flight_data.get('track')
    heading = flight_data.get('heading')
    rotation_angle = 0
    if heading is not None:
        rotation_angle = heading - 90  # Convert from map angle to SVG angle
    elif track is not None:
        rotation_angle = track - 90  # Convert from map angle to SVG angle
    
    svg += f'''    <g transform="translate({width/2}, {height/2})" filter="url(#planeShadow)">
        <!-- Plane shadow circle -->
        <circle cx="0" cy="8" r="20" fill="rgba(0,0,0,0.2)"/>
        
        <!-- Plane icon (larger, more visible, rotated based on track/heading) -->
        <g transform="rotate({rotation_angle} 0 0) scale(3) translate(-12, -12)">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" 
                  fill="url(#planeGradient)" stroke="white" stroke-width="0.5"/>
        </g>
    </g>
</svg>'''
    
    # Save to file if output_path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg)
        print(f"Map saved to: {output_path}")
    
    return svg




def main():
    """Generate a map section with flight location"""
    parser = argparse.ArgumentParser(description='Generate an SVG map section with flight location')
    parser.add_argument('--output', '-o', default=None,
                       help='Output file path (default: test_map.png for PNG, test_map.svg for SVG)')
    parser.add_argument('--lat', type=float, required=True,
                       help='Latitude of flight location')
    parser.add_argument('--lon', type=float, required=True,
                       help='Longitude of flight location')
    parser.add_argument('--callsign', default='N/A',
                       help='Flight callsign')
    parser.add_argument('--altitude', type=int,
                       help='Altitude in feet')
    parser.add_argument('--speed', type=float,
                       help='Speed in knots')
    parser.add_argument('--track', type=float,
                       help='Track/heading in degrees (direction of movement)')
    parser.add_argument('--heading', type=float,
                       help='Heading in degrees (direction nose is pointing)')
    parser.add_argument('--width', type=int, default=800,
                       help='Map width in pixels (default: 800, fixed)')
    parser.add_argument('--height', type=int, default=480,
                       help='Map height in pixels (default: 480, fixed)')
    parser.add_argument('--zoom', type=int, default=12,
                       help='Zoom level 1-18 (default: 12, higher = more zoomed in)')
    parser.add_argument('--format', choices=['png', 'svg'], default='png',
                       help='Output format: png (OpenStreetMap) or svg (simplified map)')
    parser.add_argument('--overlay-card', action='store_true',
                       help='Overlay flight information card on the map (requires cairosvg)')
    parser.add_argument('--inky', action='store_true',
                       help='Convert image to Inky Impression 73 color palette (black, white, red, green, blue, yellow)')
    parser.add_argument('--origin', help='Origin airport code')
    parser.add_argument('--destination', help='Destination airport code')
    parser.add_argument('--origin-country', help='Origin country name')
    parser.add_argument('--destination-country', help='Destination country name')
    parser.add_argument('--icao', help='ICAO code')
    parser.add_argument('--vertical-rate', type=int, help='Vertical rate in ft/min')
    parser.add_argument('--distance', type=float, help='Distance from receiver in km')
    parser.add_argument('--squawk', help='Squawk code')
    parser.add_argument('--aircraft-model', help='Aircraft model')
    parser.add_argument('--aircraft-type', help='Aircraft type')
    parser.add_argument('--aircraft-registration', help='Aircraft registration')
    parser.add_argument('--airline-logo', help='Airline logo URL')
    parser.add_argument('--airline-code', help='Airline code')
    parser.add_argument('--airline-name', help='Airline name')
    parser.add_argument('--status', default='saved', choices=['new', 'saved'],
                       help='Flight status (default: saved)')
    
    args = parser.parse_args()
    
    # Set default output filename based on format
    if args.output is None:
        if args.format == 'png':
            args.output = 'test_map.png'
        else:
            args.output = 'test_map.svg'
    
    # Flight data
    flight = {
        'lat': args.lat,
        'lon': args.lon,
        'callsign': args.callsign,
        'altitude': args.altitude,
        'speed': args.speed,
        'track': args.track,
        'heading': args.heading,
        'icao': args.icao,
        'origin': args.origin,
        'destination': args.destination,
        'origin_country': args.origin_country,
        'destination_country': args.destination_country,
        'vertical_rate': args.vertical_rate,
        'distance': args.distance,
        'squawk': args.squawk,
        'aircraft_model': args.aircraft_model,
        'aircraft_type': args.aircraft_type,
        'aircraft_registration': args.aircraft_registration,
        'airline_logo': args.airline_logo,
        'airline_code': args.airline_code,
        'airline_name': args.airline_name,
        'status': args.status
    }
    
    # Calculate distance if lat/lon are provided (for flight card)
    if args.lat and args.lon and not flight.get('distance'):
        # You could calculate distance to a reference point here if needed
        pass
    
    # Generate map based on format
    if args.format == 'png':
        # Try to generate PNG with OpenStreetMap
        if not HAS_PIL:
            print("Error: PIL/Pillow is required for PNG generation.", file=sys.stderr)
            print("Install it with: pip install pillow requests", file=sys.stderr)
            print("Falling back to SVG format...", file=sys.stderr)
            args.format = 'svg'
            args.output = args.output.replace('.png', '.svg')
        elif not HAS_REQUESTS:
            print("Error: requests library is required for PNG generation.", file=sys.stderr)
            print("Install it with: pip install requests pillow", file=sys.stderr)
            print("Falling back to SVG format...", file=sys.stderr)
            args.format = 'svg'
            args.output = args.output.replace('.png', '.svg')
        else:
            success = generate_osm_map_png(flight, args.output, args.width, args.height, args.zoom, 
                                          overlay_card=args.overlay_card, inky_mode=args.inky)
            if success:
                print(f"Generated map PNG: {args.output}")
                print(f"  Location: {args.lat:.6f}, {args.lon:.6f}")
                print(f"  Size: {args.width}x{args.height}px")
                print(f"  Zoom: {args.zoom}")
                if args.inky:
                    print(f"  Colors: Converted to Inky Impression 73 palette")
                return 0
            else:
                print("Warning: PNG generation failed, falling back to SVG...", file=sys.stderr)
                args.format = 'svg'
                args.output = args.output.replace('.png', '.svg')
    
    # Generate SVG (either requested or as fallback)
    if args.format == 'svg':
        try:
            svg_content = generate_map_svg(flight, args.output, args.width, args.height, args.zoom)
            print(f"Generated map SVG: {args.output}")
            print(f"  Location: {args.lat:.6f}, {args.lon:.6f}")
            print(f"  Size: {args.width}x{args.height}px")
            print(f"  Zoom: {args.zoom}")
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

