# Flight Tracking Schema - Complete Setup

## 🎉 Setup Complete!

Your flight tracker now has a proper flight-centric database that tracks individual flights and aircraft separately.

## 📋 What Was Done

### ✅ Phase 1: Database Schema (COMPLETE)

Created 4 tables:
1. **aircraft** - One row per aircraft (ICAO24)
2. **flights** - One row per flight instance  
3. **positions** - Time-series position data
4. **flight_events** - Flight event logging

### ✅ Phase 2: Code Integration (COMPLETE)

- Added methods to `flight_db.py` for managing the new schema
- Integrated tracking into `flight_tracker_server.py`
- Automatic flight detection and position recording
- Callsign change detection (creates new flight)
- Graceful error handling

### ✅ Phase 3: Tools & Documentation (COMPLETE)

- `inspect_flight_db.py` - Database inspection tool
- `FLIGHT_SCHEMA_MIGRATION.md` - Technical details
- `SETUP_COMPLETE.md` - Complete guide
- `QUICK_START.md` - Quick reference
- This README

## 🚀 How to Use

### 1. Start the Server

```bash
python3 flight_tracker_server.py
```

That's it! The new schema is automatically initialized and tracking begins.

### 2. Monitor Data Collection

```bash
# View statistics
python3 inspect_flight_db.py

# View specific flight
python3 inspect_flight_db.py --flight 1
```

### 3. Query the Database

```bash
sqlite3 flights.db
```

```sql
-- Active flights right now
SELECT f.callsign, a.icao, a.registration, f.origin, f.destination, f.start_time
FROM flights f
JOIN aircraft a ON f.aircraft_icao = a.icao
WHERE f.end_time IS NULL;

-- All aircraft we've tracked
SELECT icao, registration, model, first_seen_at, last_seen_at
FROM aircraft
ORDER BY last_seen_at DESC;

-- Position history for a flight
SELECT ts, lat, lon, altitude, speed
FROM positions
WHERE flight_id = 1
ORDER BY ts;
```

## 🔑 Key Concepts

### ICAO24 (Aircraft Identifier)

- **What**: Mode S hex code from ADS-B transponder
- **Example**: `a12345`, `3c55c7`
- **Unique to**: Each aircraft/transponder
- **In code**: The `icao` field
- **Think of it as**: License plate for aircraft

### Flight (Journey Instance)

- **What**: A specific journey with a callsign
- **Example**: `UAL123` on Jan 6, 2025
- **Unique to**: Each journey
- **In database**: `flights` table with unique ID
- **Think of it as**: A trip in that aircraft

### Why This Matters

- Same aircraft can fly multiple flights
- Same callsign is reused daily (UAL123 flies every day)
- Now we can track: "This specific UAL123 flight on Jan 6"
- We can see: "All flights this aircraft has made"

## 📊 Database Schema

```
aircraft (one per plane)
├── icao (PRIMARY KEY)
├── registration (tail number)
├── type, model, manufacturer
└── first_seen_at, last_seen_at

flights (one per journey)
├── id (PRIMARY KEY)
├── aircraft_icao → aircraft.icao
├── callsign
├── origin, destination
├── start_time, end_time
└── status

positions (time-series data)
├── id (PRIMARY KEY)
├── flight_id → flights.id
├── ts (timestamp)
├── lat, lon, altitude, speed
└── track, heading, vertical_rate

flight_events (important moments)
├── id (PRIMARY KEY)
├── flight_id (optional)
├── aircraft_icao
├── event_type
└── ts, event_data
```

## 🔄 Flight Detection Logic

A new flight is created when:

1. **New ICAO24 detected**
   - First time we see this aircraft
   - Creates aircraft + flight

2. **Callsign changes**
   - Same aircraft, different callsign
   - Ends old flight, starts new one
   - Example: Aircraft changes from UAL123 to UAL456

3. **Time gap** (future enhancement)
   - Same aircraft reappears after >30 minutes
   - Likely a different flight

## 📁 Files Modified/Created

### Modified
- `flight_db.py` - Added new schema and methods
- `flight_tracker_server.py` - Added flight tracking

### Created
- `inspect_flight_db.py` - Database inspector
- `FLIGHT_SCHEMA_MIGRATION.md` - Technical guide
- `SETUP_COMPLETE.md` - Complete documentation
- `QUICK_START.md` - Quick reference
- `README_NEW_SCHEMA.md` - This file

## 🔍 Inspection Tool Usage

```bash
# Basic statistics
python3 inspect_flight_db.py

# Specific flight details
python3 inspect_flight_db.py --flight 5

# Custom database path
python3 inspect_flight_db.py /path/to/flights.db
```

## ⚠️ Important Notes

### Backward Compatibility

- **Old system still works!** Both run in parallel
- `flight_snapshots` table still being populated
- Current replay page (`index-replay.html`) unchanged
- No data loss, no breaking changes

### Data Sources

- **ADS-B data**: From dump1090 (ICAO24, callsign, position, altitude, speed)
- **Route info**: From adsb.lol API (free, no API key needed)
- **Aircraft info**: From adsb.lol API (registration, model, type)
- **No FlightAware API**: As requested, we don't use paid APIs

### Performance

- Minimal overhead (just a few extra INSERT queries per aircraft)
- Efficient indexes on all key fields
- Graceful error handling (won't crash on DB errors)
- Same cleanup schedule as before

## 🎯 Next Steps

### Immediate (You Can Do Now)

1. ✅ Run the server
2. ✅ Use inspection tool to verify data
3. ✅ Run SQL queries to explore

### Coming Soon (TODO)

1. **New API endpoints** for querying flights/aircraft
2. **New replay UI** to replace old snapshot-based replay
3. **Backfill tool** to migrate old snapshots (optional)
4. **Enhanced features** like flight statistics, heatmaps, etc.

## 🐛 Troubleshooting

### No Data Showing Up

```bash
# Check if server is running
ps aux | grep flight_tracker_server

# Check database exists and has tables
sqlite3 flights.db ".tables"

# Check for errors in server output
tail -f /path/to/server/output
```

### Database Errors

```bash
# Check permissions
ls -la flights.db

# Check disk space
df -h

# Recreate database (will lose data!)
rm flights.db
python3 flight_tracker_server.py
```

### Old Replay Not Working

The old system should still work! Check:
- Browser console for errors
- `flight_snapshots` table has data: `SELECT COUNT(*) FROM flight_snapshots;`
- Server is responding to `/api/replay` endpoints

## 📚 Documentation Files

- **QUICK_START.md** - Start here! Quick reference
- **SETUP_COMPLETE.md** - Complete setup guide
- **FLIGHT_SCHEMA_MIGRATION.md** - Technical details
- **README_NEW_SCHEMA.md** - This file (overview)

## ✨ Benefits

1. **Proper flight tracking** - Each flight is a distinct entity
2. **Aircraft history** - See all flights for any aircraft
3. **Better queries** - Find flights by callsign, route, time range
4. **Efficient storage** - No duplicate aircraft info
5. **Future-proof** - Easy to add new features
6. **Free APIs only** - No FlightAware costs

## 🎓 Example Queries

```sql
-- Busiest aircraft (most flights)
SELECT aircraft_icao, COUNT(*) as flight_count
FROM flights
GROUP BY aircraft_icao
ORDER BY flight_count DESC
LIMIT 10;

-- Flights by route
SELECT COUNT(*) as count, origin, destination
FROM flights
WHERE origin IS NOT NULL AND destination IS NOT NULL
GROUP BY origin, destination
ORDER BY count DESC;

-- Average flight duration (for completed flights)
SELECT AVG(JULIANDAY(end_time) - JULIANDAY(start_time)) * 24 as avg_hours
FROM flights
WHERE end_time IS NOT NULL;

-- Position density (positions per flight)
SELECT f.callsign, COUNT(p.id) as positions
FROM flights f
LEFT JOIN positions p ON f.id = p.flight_id
GROUP BY f.id
ORDER BY positions DESC
LIMIT 10;
```

---

## 🚀 Ready to Go!

Everything is set up and ready. Just run your server and the new tracking will happen automatically in the background!

```bash
python3 flight_tracker_server.py
```

Then monitor with:

```bash
python3 inspect_flight_db.py
```

Enjoy your new flight tracking system! ✈️

