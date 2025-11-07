# Flight Tracker

A real-time flight tracking system that collects ADS-B data from dump1090 and displays it via terminal and web interface with optional map visualization.

## Features

- **Data Collection**: Fetches aircraft data from dump1090
- **Route Enrichment**: Looks up origin/destination using adsb.lol API
- **Web Interface**: Modern, responsive web UI for flight visualization
- **Interactive Maps**: Optional Leaflet-based map showing aircraft positions and routes
- **Real-time Updates**: Live updates via WebSocket
- **Unified Server**: Single program handles everything (HTTP + WebSocket + data collection)

## Architecture

The project includes three main scripts:

```
flight_server.py (unified server)
    ├── HTTP server (serves web interface)
    ├── WebSocket server (real-time updates)
    └── Flight data collection (from dump1090)
            ↓
    web/index.html (web client - card-based layout)

flight-maps_server.py (unified server with map support)
    ├── HTTP server (serves web interface)
    ├── WebSocket server (real-time updates)
    └── Flight data collection (from dump1090)
            ↓
    web/index-maps.html (web client - map-based visualization)

flight_tracker.py (terminal-only)
    └── Terminal output (no web interface)
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.json`:
```json
{
    "dump1090_url": "http://your-dump1090-url/data/aircraft.json",
    "receiver_lat": 52.40585,
    "receiver_lon": 13.55214,
    "hide_receiver": false,
    "show_test_flight": false,
    "http_host": "0.0.0.0",
    "http_port": 8080,
    "websocket_host": "0.0.0.0",
    "websocket_port": 8765
}
```

Configuration options:
- `dump1090_url`: URL to your dump1090 instance's aircraft.json endpoint
- `receiver_lat` / `receiver_lon`: Your receiver's GPS coordinates (for distance calculation and map centering)
- `hide_receiver`: Set to `true` to hide the receiver marker on the map (default: `false`)
- `show_test_flight`: Set to `true` to show a test flight for debugging (default: `false`)
- `http_host` / `http_port`: HTTP server bind address and port
- `websocket_host` / `websocket_port`: WebSocket server bind address and port

## Usage

### Map-Based Web Server (Recommended)

Run the unified server with interactive map support:
```bash
python3 flight-maps_server.py
```

This starts:
- HTTP server on port 8080 (serves web interface)
- WebSocket server on port 8765 (real-time updates)
- Flight data collection (fetches from dump1090 every 5 seconds)

Then open your browser to:
```
http://localhost:8080/index-maps.html
```

The map interface provides:
- Interactive Leaflet map with OpenStreetMap tiles
- Aircraft markers showing real-time positions
- Aircraft rotation based on heading/track
- Heading indicator lines
- Click aircraft markers to see detailed flight cards
- Receiver location marker (configurable)
- Airport markers (e.g., BER - Berlin Brandenburg Airport)

### Card-Based Web Server

Run the unified server with card-based layout (no map):
```bash
python3 flight_server.py
```

This starts the same servers as above, but serves:
```
http://localhost:8080/index.html
```

The card interface provides:
- Grid-based flight cards
- All flight details in compact card format
- No map visualization

### Terminal Only Mode

If you just want terminal output without the web interface:
```bash
python3 flight_tracker.py
```

## Web Interfaces

### Map Interface (`index-maps.html`)

The map-based interface provides:
- Interactive Leaflet map with real-time aircraft positions
- Aircraft markers that rotate based on heading/track direction
- Heading indicator lines showing flight direction
- Click aircraft markers to see detailed flight cards with popup
- Receiver location marker (can be hidden via config)
- Airport markers for nearby airports
- Real-time flight updates via WebSocket
- Connection status indicator
- Flight statistics

### Card Interface (`index.html`)

The card-based interface provides:
- Real-time flight updates via WebSocket
- Beautiful grid-based card layout
- Connection status indicator
- Flight statistics
- Route information (origin → destination with country flags)
- Aircraft details (altitude, speed, track, position, aircraft type)
- Airline logos

## Files

**Main Scripts:**
- `flight-maps_server.py` - Unified server with map support (HTTP + WebSocket + data collection)
- `flight_server.py` - Unified server with card-based layout (HTTP + WebSocket + data collection)
- `flight_tracker.py` - Terminal-only flight tracker

**Modules:**
- `flight_info.py` - Route lookup utilities (adsb.lol API, OpenFlights database)
- `airline_logos.py` - Airline logo/name lookup (OpenFlights database, Google favicon service)

**Web Interface:**
- `web/index-maps.html` - Map-based web interface (used by flight-maps_server.py)
- `web/index.html` - Card-based web interface (used by flight_server.py)

**Configuration & Data:**
- `config.json` - Configuration file
- `airlines_cache.dat` - Cached airline data (auto-generated)
- `airports_cache.dat` - Cached airport data (auto-generated)

## Testing

Test flight lookup manually:
```bash
python3 flight_info.py <ICAO> <CALLSIGN> [LAT] [LON]
```

Example:
```bash
python3 flight_info.py 3c55c7 EWG1AN
```

## Troubleshooting

- **WebSocket not connecting**: Check firewall settings and ensure port 8765 is open
- **No flights displayed**: Verify dump1090 URL is correct and accessible
- **Routes not found**: Ensure aircraft have callsigns and are in adsb.lol database
