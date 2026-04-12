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

Pi-Sky ships as **one program**, `flight_tracker_server.py`, that ties everything together:

```
flight_tracker_server.py
    ├── HTTP server (static files under web/, REST APIs, config)
    ├── SSE stream at /events (live flight JSON to the browser)
    └── Background flight loop (polls dump1090, enriches via APIs, optional DB snapshots)
            ↓
    web/index-maps.html   — map UI (default “full” experience)
    web/index.html        — card / list UI (split-flap section, etc.)
    web/index-replay.html — history / replay
    web/config.html       — settings UI
```

**Supporting Python modules** (imported by the server): `flight_info.py` (routes, airports), `airline_logos.py`, `flight_db.py` (SQLite history), `map_to_png.py` (e-paper map tiles), and optionally `display_inky.py` for a connected Inky panel.

**External data path:** dump1090 (or compatible feed) exposes `aircraft.json`; Pi-Sky fetches that URL and merges in third-party flight data. Live UI updates use **Server-Sent Events** (`EventSource` → `/events`), not a separate WebSocket port.

## Installation

1. **Prerequisites**
   - **Python 3** with `pip` and `venv`.
   - A running **dump1090** (or compatible) feed reachable at the URL you will put in `config.json` (Pi-Sky does not install the decoder for you).
   - On **Raspberry Pi OS / Debian**, install Cairo headers **before** `pip` so `cairosvg` can build (see `requirements.txt`):
     ```bash
     sudo apt-get update
     sudo apt-get install -y libcairo2-dev
     ```

2. **Python environment** (recommended; matches `setup_venv.sh` and the bundled systemd helpers):
   ```bash
   cd /path/to/pi-sky
   ./setup_venv.sh
   ```
   Or manually:
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install --upgrade pip
   ./venv/bin/pip install -r requirements.txt
   ```

3. **Configuration file** — copy the template and edit (see below):
   ```bash
   cp config_template.json config.json
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
- `websocket_host` / `websocket_port`: Still validated in config; **live flight updates use SSE on the HTTP port** at `/events`, not a separate WebSocket listener.

## Usage

### Map-Based Web Server (Recommended)

Run the unified server with interactive map support:
```bash
python3 flight_tracker_server.py
```

This starts:
- HTTP server on the configured port (serves the web UI and `/events`)
- SSE stream at `/events` for live updates in the browser
- Flight loop that polls dump1090 about once per second (enrichment and DB snapshot cadence may vary)

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

### Card-based layout (same server)

With `flight_tracker_server.py` already running, open the card UI at:

```
http://localhost:8080/index.html
```

Same backend as the map view; only the front-end page differs.

## Web Interfaces

### Map Interface (`index-maps.html`)

The map-based interface provides:
- Interactive Leaflet map with real-time aircraft positions
- Aircraft markers that rotate based on heading/track direction
- Heading indicator lines showing flight direction
- Click aircraft markers to see detailed flight cards with popup
- Receiver location marker (can be hidden via config)
- Airport markers for nearby airports
- Real-time flight updates via SSE (`/events`)
- Connection status indicator
- Flight statistics

### Card Interface (`index.html`)

The card-based interface provides:
- Real-time flight updates via SSE (`/events`)
- Beautiful grid-based card layout
- Connection status indicator
- Flight statistics
- Route information (origin → destination with country flags)
- Aircraft details (altitude, speed, track, position, aircraft type)
- Airline logos

## Files

**Main script:**
- `flight_tracker_server.py` — HTTP + SSE + flight collection and enrichment

**Modules:**
- `flight_info.py` — Route and airport utilities (adsb.lol API, OpenFlights data)
- `airline_logos.py` — Airline name/logo helpers
- `flight_db.py` — SQLite flight history for replay and mini-maps
- `map_to_png.py` — Raster map generation for Inky and previews
- `display_inky.py` — Optional hardware display output

**Web interface:**
- `web/index-maps.html` — Map UI
- `web/index.html` — Card / list UI
- `web/index-replay.html` — Replay / history
- `web/config.html` — Configuration

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

- **Live updates not streaming**: Confirm the browser can reach `http://<host>:<port>/events` (same origin as the UI; check reverse proxies and mixed content)
- **No flights displayed**: Verify dump1090 URL is correct and accessible
- **Routes not found**: Ensure aircraft have callsigns and are in adsb.lol database
