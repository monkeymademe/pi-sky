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

Copy the template and edit **`config.json`** (same directory as the server):

```bash
cp config_template.json config.json
```

**Required fields** (validated when saving via `/api/config`): `dump1090_url`, `receiver_lat`, `receiver_lon`. The server also expects integer `http_port` and `websocket_port` in saved configs.

The authoritative full example is **`config_template.json`** in this repo. It includes:

```json
{
    "dump1090_url": "http://localhost:8080/data/aircraft.json",
    "receiver_lat": 52.40585,
    "receiver_lon": 13.55214,
    "nearest_airport": "EDDB",
    "hide_receiver": false,
    "show_test_flight": false,
    "http_host": "0.0.0.0",
    "http_port": 5050,
    "websocket_host": "0.0.0.0",
    "websocket_port": 8765,
    "inky": { "enabled": false },
    "map_generation": {
        "min_interval_seconds": 300,
        "prefer_closest": true,
        "require_route": true,
        "min_altitude": 10000,
        "max_distance_km": 500
    },
    "clear_skies": { "enabled": true },
    "database": {
        "enabled": true,
        "db_path": "flights.db",
        "snapshot_interval_seconds": 5,
        "cleanup_days": 7
    }
}
```

**Common options**

| Key | Purpose |
|-----|--------|
| `dump1090_url` | HTTP(S) URL to `aircraft.json` from dump1090 (or compatible). |
| `receiver_lat` / `receiver_lon` | Your antenna position (maps, distance, clear-skies centering). |
| `nearest_airport` | Optional ICAO/IATA code for labels and clear-skies context. |
| `hide_receiver` | Hide the receiver marker on the map. |
| `show_test_flight` | Inject a test aircraft for UI debugging. |
| `http_host` / `http_port` | Bind address and port for the web UI and **`/events` (SSE)**. If omitted at startup, the server defaults to `0.0.0.0:8080`. |
| `websocket_host` / `websocket_port` | Must be integers when present; **not used for live updates** — the browser uses **SSE** on the HTTP port at `/events`. |
| `inky.enabled` | When `true`, generate `inky_ready.png` and optional Inky hardware output (see template defaults). |
| `map_generation.*` | Intervals and filters for automatic e-paper map updates (when `inky.enabled` is `true`). |
| `clear_skies` | Clear-skies / idle map behaviour (with `nearest_airport` and cached coords as applicable). |
| `database.*` | SQLite flight history, snapshot interval, and retention for replay / mini-maps. |

Use the **config page** in the web UI (`config.html`) or edit `config.json` directly; saving through the API validates types and required keys.

## Usage

Run the server from the **project directory** (it loads `config.json` and serves `web/` relative to the current working directory).

```bash
cd /path/to/pi-sky
./venv/bin/python3 flight_tracker_server.py
```

If you use a venv, activate it first, or call `./venv/bin/python3` as above. With dependencies installed globally, `python3 flight_tracker_server.py` is fine.

**What starts**

- HTTP server on **`http_host`:`http_port`** (from `config.json`; template default **5050**, or **8080** if those keys are omitted at startup)
- **SSE** live stream at **`/events`** on that same port
- Background loop that polls dump1090 about **once per second** (API enrichment and DB snapshots run on their own cadence)

**URLs** (replace host/port with your settings; same origin as the UI for `/events`):

| Page | Path |
|------|------|
| Map (main) | `http://<host>:<port>/index-maps.html` |
| Card / list UI | `http://<host>:<port>/index.html` |
| Replay / history | `http://<host>:<port>/index-replay.html` |
| Settings | `http://<host>:<port>/config.html` |

Example for a Pi on the LAN with default template port: `http://192.168.1.10:5050/index-maps.html`.

**systemd (optional)** — install and enable the bundled unit so Pi-Sky starts at boot (expects `/home/pi/pi-sky` and `venv`):

```bash
sudo ./install_service.sh
sudo systemctl start flight-tracker
```

**Kiosk / fullscreen browser (optional)** — on a desktop session, `start_kiosk.sh` opens Chromium pointed at the map URL (see script for details).

### Map view (recommended entry point)

The map UI (`index-maps.html`) includes:

- Leaflet map (OpenStreetMap tiles), aircraft markers, heading lines, popups
- Receiver marker (optional hide via config) and airport markers when configured

### Card layout

Same server; open `index.html` for the grid / split-flap style layout without the main map chrome.

## Web interfaces (detail)

All pages use the same SSE stream (`/events`) and backend.

- **`index-maps.html`** — Full-screen map, aircraft popups, statistics.
- **`index.html`** — Card grid, route lines, airline logos, split-flap section for the latest flight.
- **`index-replay.html`** — Browse stored flights and replay tracks (requires database enabled).
- **`config.html`** — Edit settings and POST to `/api/config`.

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
