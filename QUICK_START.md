# Quick Start Guide

## What Changed?

Your flight tracker now properly tracks **individual flights** instead of just snapshots.

### Key Concept: ICAO vs Flight

- **ICAO24** (`icao` field): Unique to each **aircraft** (like a license plate)
- **Flight**: A specific journey (like a trip in that car)
- Same aircraft can make multiple flights
- Same callsign (like "UAL123") is reused daily

## Start Tracking

```bash
# Just run your server as normal
python3 flight_tracker_server.py
```

The new tracking happens automatically in the background!

## Check What's Being Tracked

```bash
# View statistics
python3 inspect_flight_db.py

# View a specific flight
python3 inspect_flight_db.py --flight 1
```

## Example Output

```
✈️  AIRCRAFT
   Total aircraft: 5
   
   Recent aircraft:
   • a12345 - N12345 (Boeing 737-800)
     First seen: 2025-01-06T10:30:00
     Last seen:  2025-01-06T11:45:00

🛫 FLIGHTS
   Total flights: 8
   Active flights: 3
   Ended flights: 5
   
   Active flights:
   • Flight #7: UAL123 (a12345)
     Route: SFO → LAX
     Aircraft: N12345 (Boeing 737-800)
     Started: 2025-01-06T11:30:00
     Status: airborne

📍 POSITIONS
   Total positions: 1,234
```

## What to Look For

### ✅ Good Signs
- Aircraft count increases as you see new planes
- Active flights show current aircraft
- Position counts grow over time
- Flights have route info (origin → destination)

### ⚠️ Warning Signs
- No aircraft after 5 minutes → Check dump1090 connection
- No positions → Check database permissions
- Errors in server output → Check logs

## Database Tables

You now have 4 tables:

1. **aircraft** - One row per plane
2. **flights** - One row per journey
3. **positions** - Time-series data (lat/lon/alt/speed)
4. **flight_events** - Important moments (new flight, route found, etc.)

## Old vs New

### Old System (Still Works!)
- `flight_snapshots` table
- Used by current replay page
- Still being populated

### New System (Now Active!)
- `aircraft`, `flights`, `positions` tables
- Proper flight tracking
- Ready for new replay UI

## Next Steps

1. **Run the server** - Let it collect data
2. **Monitor with inspector** - Check `inspect_flight_db.py` periodically
3. **Wait for new UI** - New replay interface coming soon

## Quick SQL Queries

```bash
sqlite3 flights.db
```

```sql
-- How many aircraft have we seen?
SELECT COUNT(*) FROM aircraft;

-- What's flying now?
SELECT callsign, aircraft_icao, origin, destination 
FROM flights 
WHERE end_time IS NULL;

-- Show me all flights for aircraft abc123
SELECT * FROM flights WHERE aircraft_icao = 'abc123';

-- How many positions do we have?
SELECT COUNT(*) FROM positions;
```

## Troubleshooting

**"No aircraft showing up"**
- Check dump1090 is running
- Verify config.json has correct dump1090_url
- Check server output for connection errors

**"Database errors in logs"**
- Check file permissions on flights.db
- Verify disk space available
- Try deleting flights.db and restart (will recreate)

**"Old replay page not working"**
- Old system still works! Both run in parallel
- Check browser console for errors
- Verify database has data: `SELECT COUNT(*) FROM flight_snapshots;`

## Support

Check these files for more info:
- `SETUP_COMPLETE.md` - Full setup documentation
- `FLIGHT_SCHEMA_MIGRATION.md` - Technical details
- `inspect_flight_db.py` - Database inspection tool

---

**You're all set! Just run the server and watch the flights roll in! ✈️**

