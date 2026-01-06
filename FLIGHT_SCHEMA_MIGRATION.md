# Flight Schema Migration

## Overview

We've migrated from a snapshot-based replay system to a flight-centric database schema that properly tracks individual flights and aircraft.

## Key Changes

### Database Schema

#### New Tables

1. **`aircraft`** - One row per ICAO24 (unique per aircraft/transponder)
   - `icao` (PRIMARY KEY) - ICAO24 hex code
   - `registration` - Aircraft registration (tail number)
   - `type` - Aircraft type code
   - `model` - Aircraft model/description
   - `manufacturer` - Aircraft manufacturer
   - `first_seen_at` - First time we detected this aircraft
   - `last_seen_at` - Most recent detection

2. **`flights`** - One row per flight instance
   - `id` (PRIMARY KEY)
   - `aircraft_icao` - Links to aircraft table
   - `callsign` - Flight callsign (can be NULL for unidentified)
   - `origin` - Origin airport code
   - `destination` - Destination airport code
   - `origin_country` - Origin country
   - `destination_country` - Destination country
   - `airline_code` - Airline ICAO/IATA code
   - `airline_name` - Airline name
   - `start_time` - When flight was first detected
   - `end_time` - When flight ended (NULL while active)
   - `status` - Flight status (airborne/landed/callsign_change)

3. **`positions`** - Time-series position data for each flight
   - `id` (PRIMARY KEY)
   - `flight_id` - Links to flights table
   - `ts` - Timestamp
   - `lat`, `lon` - Position
   - `altitude` - Altitude in feet
   - `speed` - Ground speed in knots
   - `track` - Track angle
   - `heading` - Magnetic heading
   - `vertical_rate` - Rate of climb/descent
   - `squawk` - Transponder code
   - `distance` - Distance from receiver

4. **`flight_events`** - Enhanced to support flight_id
   - Existing table now supports both old (icao-based) and new (flight_id-based) events

### Important Concepts

**ICAO24 vs Flight:**
- **ICAO24** (Mode S hex): Unique identifier for each aircraft/transponder
  - Example: `3c55c7`
  - Same aircraft can fly multiple flights
- **Flight**: A specific journey with a callsign
  - Example: `UAL123` on 2025-01-06
  - Same callsign is reused daily by different flights

**Flight Detection:**
- New flight is created when:
  1. New ICAO24 is detected
  2. Callsign changes for existing ICAO24
  3. Time gap > 30 minutes (future enhancement)

### Code Changes

#### `flight_db.py`

Added new methods:
- `_init_new_schema()` - Creates new tables
- `upsert_aircraft()` - Insert/update aircraft records
- `get_active_flight()` - Get currently active flight for an aircraft
- `start_flight()` - Create new flight record
- `end_flight()` - Mark flight as ended
- `update_flight_info()` - Update flight details (origin/destination)
- `insert_position()` - Insert position record
- `log_flight_event()` - Log flight events

#### `flight_tracker_server.py`

Added flight tracking in `process_aircraft_data()`:
- After enriched data is fully populated
- Updates aircraft record
- Creates or updates active flight
- Detects callsign changes (new flight)
- Inserts position data
- Handles errors gracefully

### Backward Compatibility

The old `flight_snapshots` table is **still active** and continues to be populated. This ensures:
- Existing replay functionality continues to work
- No data loss during migration
- Time to test new schema before switching

### Next Steps

1. **Test the new schema** - Run the server and verify data is being written
2. **Create new API endpoints:**
   - `GET /api/flights` - List flights
   - `GET /api/flights/{id}` - Get flight details
   - `GET /api/flights/{id}/positions` - Get flight positions
   - `GET /api/aircraft` - List aircraft
   - `GET /api/aircraft/{icao}` - Get aircraft details
3. **Build new replay UI** - Replace `index-replay.html` with flight-based UI
4. **Backfill data** - Migrate existing snapshots to new schema (optional)
5. **Retire old schema** - Once confident, stop writing to `flight_snapshots`

## Usage

The new schema is automatically initialized when the database is created. No manual migration needed.

To verify it's working:

```bash
# Check the database
sqlite3 flights.db

# List tables
.tables

# Check aircraft
SELECT * FROM aircraft LIMIT 5;

# Check flights
SELECT * FROM flights LIMIT 5;

# Check positions
SELECT COUNT(*) FROM positions;

# See active flights
SELECT f.id, f.callsign, a.icao, a.registration, f.start_time, f.status
FROM flights f
JOIN aircraft a ON f.aircraft_icao = a.icao
WHERE f.end_time IS NULL;
```

## Benefits

1. **Proper flight tracking** - Each flight is a distinct entity
2. **Aircraft history** - See all flights for a specific aircraft
3. **Better queries** - Find flights by callsign, route, time range
4. **Efficient storage** - No duplicate aircraft info in every snapshot
5. **Future-proof** - Can add features like flight paths, statistics, etc.

