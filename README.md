# Pi-Sky

![Pi-Sky logo](web/assets/pi-sky-logo.svg)

**Pi-Sky** is a real-time flight-tracking web UI for the **Raspberry Pi**.

Aircraft broadcast ADS-B messages on 1090 MHz, often several times per second, carrying basic information about each flight, including:

- **ICAO address** — a unique hex identifier for that aircraft's transponder.
- **Callsign** — the flight ID (e.g. airline + flight number), when set.
- **Position** — latitude and longitude from the aircraft's GPS.
- **Altitude** — pressure altitude.
- **Speed and track** — ground speed and the direction the aircraft is moving over the ground.
- **Vertical rate** — climb or descent in feet per minute (or level).
- **Squawk code** — the transponder code (e.g. 1200 for VFR in many places), when transmitted.

When an aircraft is **within range** of your antenna, **dump1090** listens for those **1090 MHz** bursts and **decodes** them. That decoded stream is what feeds local tools and what people often **upload** to global tracking networks like FlightAware, Flightradar24 and ADS-B Exchange — essentially crowdsourced coverage built from many receivers worldwide.

**Pi-Sky** reads **dump1090** data from **your** receiver, enriches it with **third-party APIs** (for example route and aircraft details), and serves everything to the browser. **Your data stays local** unless you separately choose to feed another service.

## Features

- **Simple local web UI** served from the Raspberry Pi.
- **API-backed enrichment** (e.g. origin/destination and extra flight context).
- **Live interactive map** of aircraft your receiver is detecting.
- **Optional Pimoroni Inky e-paper support** — generate map images for a connected Inky display (when enabled in config and hardware is present).
- **SQLite database** with **configurable** retention (e.g. **7 days** of position history by default).
- **Mini maps** for individual past flights.
- **Full-map replay** for reviewing a day or week's traffic.

## Architecture

The project includes three main scripts:

```
flight_server.py (unified server)
    ├── HTTP server (serves web interface)
    ├── WebSocket server (real-time updates)
    └── Flight data collection (from dump1090)
            ↓
    web/index.html (web client - card-based layout)

flight_tracker_server.py (unified server with map support)
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
python3 flight_tracker_server.py
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
- `flight_tracker_server.py` - Unified server with map support (HTTP + WebSocket + data collection)
- `flight_server.py` - Unified server with card-based layout (HTTP + WebSocket + data collection)
- `flight_tracker.py` — Terminal-only Pi-Sky / dump1090 viewer

**Modules:**
- `flight_info.py` - Route lookup utilities (adsb.lol API, OpenFlights database)
- `airline_logos.py` - Airline logo/name lookup (OpenFlights database, Google favicon service)

**Web Interface:**
- `web/index-maps.html` - Map-based web interface (used by flight_tracker_server.py)
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
