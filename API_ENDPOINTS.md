# Flight Tracking API Endpoints

## Overview

New REST API endpoints for querying flights, aircraft, and positions. These endpoints provide access to the new flight-centric database schema.

## Base URL

All endpoints are under `/api/` prefix.

Example: `http://localhost:8080/api/flights`

## Endpoints

### Flights API

#### 1. List Flights
**GET** `/api/flights`

Get a list of flights with optional filters.

**Query Parameters:**
- `start_time` (optional) - Filter flights starting after this time (ISO format)
- `end_time` (optional) - Filter flights ending before this time (ISO format)
- `callsign` (optional) - Filter by callsign (e.g., "UAL123")
- `icao` (optional) - Filter by aircraft ICAO code (e.g., "a12345")
- `active_only` (optional) - If `true`, only return active flights (default: `false`)
- `limit` (optional) - Limit number of results (default: no limit)

**Example:**
```
GET /api/flights?active_only=true&limit=10
GET /api/flights?callsign=UAL123
GET /api/flights?icao=a12345&start_time=2025-01-06T00:00:00
```

**Response:**
```json
{
  "flights": [
    {
      "id": 1,
      "callsign": "UAL123",
      "aircraft_icao": "a12345",
      "aircraft": {
        "icao": "a12345",
        "registration": "N12345",
        "type": "B738",
        "model": "Boeing 737-800",
        "manufacturer": null
      },
      "origin": "SFO",
      "destination": "LAX",
      "origin_country": "United States",
      "destination_country": "United States",
      "airline_code": "UAL",
      "airline_name": "United Airlines",
      "start_time": "2025-01-06T10:00:00",
      "end_time": "2025-01-06T11:30:00",
      "status": "landed",
      "position_count": 540
    }
  ],
  "count": 1
}
```

#### 2. Get Flight Details
**GET** `/api/flights/{id}`

Get detailed information about a specific flight.

**Example:**
```
GET /api/flights/1
```

**Response:**
```json
{
  "id": 1,
  "callsign": "UAL123",
  "aircraft_icao": "a12345",
  "aircraft": {
    "icao": "a12345",
    "registration": "N12345",
    "type": "B738",
    "model": "Boeing 737-800",
    "manufacturer": null
  },
  "origin": "SFO",
  "destination": "LAX",
  "origin_country": "United States",
  "destination_country": "United States",
  "airline_code": "UAL",
  "airline_name": "United Airlines",
  "start_time": "2025-01-06T10:00:00",
  "end_time": "2025-01-06T11:30:00",
  "status": "landed",
  "position_count": 540
}
```

#### 3. Get Flight Positions
**GET** `/api/flights/{id}/positions`

Get all position data for a flight. Perfect for plotting on a map!

**Query Parameters:**
- `start_time` (optional) - Filter positions after this time (ISO format)
- `end_time` (optional) - Filter positions before this time (ISO format)
- `limit` (optional) - Limit number of positions (default: all)

**Example:**
```
GET /api/flights/1/positions
GET /api/flights/1/positions?limit=100
GET /api/flights/1/positions?start_time=2025-01-06T10:30:00
```

**Response:**
```json
{
  "flight_id": 1,
  "callsign": "UAL123",
  "aircraft_icao": "a12345",
  "origin": "SFO",
  "destination": "LAX",
  "start_time": "2025-01-06T10:00:00",
  "end_time": "2025-01-06T11:30:00",
  "status": "landed",
  "positions": [
    {
      "ts": "2025-01-06T10:00:00",
      "lat": 37.6213,
      "lon": -122.379,
      "altitude": 1000,
      "speed": 150,
      "track": 87.5,
      "heading": 87.5,
      "vertical_rate": 500,
      "squawk": "1234",
      "distance": 2.5
    },
    {
      "ts": "2025-01-06T10:00:05",
      "lat": 37.6215,
      "lon": -122.380,
      "altitude": 1500,
      "speed": 180,
      "track": 87.6,
      "heading": 87.6,
      "vertical_rate": 400,
      "squawk": "1234",
      "distance": 2.8
    }
  ],
  "count": 540
}
```

**Use Case: Plotting on Map**
```javascript
// Fetch flight positions
const response = await fetch('/api/flights/1/positions');
const data = await response.json();

// Extract coordinates
const path = data.positions.map(p => [p.lat, p.lon]);

// Draw on Leaflet map
const polyline = L.polyline(path, {
  color: 'blue',
  weight: 3,
  opacity: 0.7
}).addTo(map);
```

### Aircraft API

#### 4. List Aircraft
**GET** `/api/aircraft`

Get a list of all aircraft we've tracked.

**Query Parameters:**
- `limit` (optional) - Limit number of results (default: all)

**Example:**
```
GET /api/aircraft
GET /api/aircraft?limit=20
```

**Response:**
```json
{
  "aircraft": [
    {
      "icao": "a12345",
      "registration": "N12345",
      "type": "B738",
      "model": "Boeing 737-800",
      "manufacturer": null,
      "first_seen_at": "2025-01-06T08:00:00",
      "last_seen_at": "2025-01-06T12:00:00"
    }
  ],
  "count": 1
}
```

#### 5. Get Aircraft Details
**GET** `/api/aircraft/{icao}`

Get detailed information about a specific aircraft.

**Example:**
```
GET /api/aircraft/a12345
```

**Response:**
```json
{
  "icao": "a12345",
  "registration": "N12345",
  "type": "B738",
  "model": "Boeing 737-800",
  "manufacturer": null,
  "first_seen_at": "2025-01-06T08:00:00",
  "last_seen_at": "2025-01-06T12:00:00"
}
```

#### 6. Get Aircraft Flights
**GET** `/api/aircraft/{icao}/flights`

Get all flights for a specific aircraft.

**Query Parameters:**
- `limit` (optional) - Limit number of flights (default: all)

**Example:**
```
GET /api/aircraft/a12345/flights
GET /api/aircraft/a12345/flights?limit=10
```

**Response:**
```json
{
  "aircraft": {
    "icao": "a12345",
    "registration": "N12345",
    "type": "B738",
    "model": "Boeing 737-800",
    "manufacturer": null,
    "first_seen_at": "2025-01-06T08:00:00",
    "last_seen_at": "2025-01-06T12:00:00"
  },
  "flights": [
    {
      "id": 1,
      "callsign": "UAL123",
      "origin": "SFO",
      "destination": "LAX",
      "start_time": "2025-01-06T10:00:00",
      "end_time": "2025-01-06T11:30:00",
      "status": "landed"
    },
    {
      "id": 2,
      "callsign": "UAL456",
      "origin": "LAX",
      "destination": "SFO",
      "start_time": "2025-01-06T14:00:00",
      "end_time": null,
      "status": "airborne"
    }
  ],
  "count": 2
}
```

## Error Responses

All endpoints return standard HTTP status codes:

- **200 OK** - Request successful
- **404 Not Found** - Flight or aircraft not found
- **500 Internal Server Error** - Server error
- **503 Service Unavailable** - Database not enabled or not found

Error response format:
```json
{
  "error": "Error type",
  "message": "Detailed error message"
}
```

## Examples

### Get Active Flights
```bash
curl "http://localhost:8080/api/flights?active_only=true"
```

### Get Flight Path for Map
```bash
curl "http://localhost:8080/api/flights/1/positions"
```

### Get All Flights for an Aircraft
```bash
curl "http://localhost:8080/api/aircraft/a12345/flights"
```

### Find Flights by Callsign
```bash
curl "http://localhost:8080/api/flights?callsign=UAL123"
```

### Get Flights in Time Range
```bash
curl "http://localhost:8080/api/flights?start_time=2025-01-06T00:00:00&end_time=2025-01-06T23:59:59"
```

## JavaScript Examples

### Fetch and Plot Flight Path
```javascript
async function plotFlightPath(flightId) {
  // Get flight positions
  const response = await fetch(`/api/flights/${flightId}/positions`);
  const data = await response.json();
  
  // Extract coordinates
  const path = data.positions.map(p => [p.lat, p.lon]);
  
  // Draw on Leaflet map
  const polyline = L.polyline(path, {
    color: 'blue',
    weight: 3,
    opacity: 0.7
  }).addTo(map);
  
  // Fit map to path
  map.fitBounds(polyline.getBounds());
  
  return data;
}
```

### List Active Flights
```javascript
async function getActiveFlights() {
  const response = await fetch('/api/flights?active_only=true&limit=20');
  const data = await response.json();
  
  console.log(`Found ${data.count} active flights`);
  data.flights.forEach(flight => {
    console.log(`${flight.callsign}: ${flight.origin} → ${flight.destination}`);
  });
  
  return data.flights;
}
```

### Get Aircraft History
```javascript
async function getAircraftHistory(icao) {
  const response = await fetch(`/api/aircraft/${icao}/flights`);
  const data = await response.json();
  
  console.log(`Aircraft ${icao} has made ${data.count} flights`);
  console.log(`Registration: ${data.aircraft.registration}`);
  console.log(`Model: ${data.aircraft.model}`);
  
  return data.flights;
}
```

## Notes

- All timestamps are in ISO 8601 format
- Position data is stored chronologically (ordered by `ts`)
- Flight status can be: `airborne`, `landed`, `callsign_change`, `unknown`
- Positions include: lat, lon, altitude, speed, track, heading, vertical_rate, squawk, distance
- All endpoints return JSON
- CORS is enabled (if your server supports it)

## Next Steps

These endpoints are ready to use! You can now:

1. **Query flights** - Find flights by callsign, ICAO, time range
2. **Get flight paths** - Perfect for plotting on maps
3. **Track aircraft** - See all flights for a specific aircraft
4. **Build new UI** - Create a new replay interface using these endpoints

