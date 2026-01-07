#!/usr/bin/env python3
"""
Backfill Tool: Migrate old flight_snapshots data to new flight-centric schema

This script reads data from the old flight_snapshots table and migrates it to:
- aircraft table (one row per ICAO24)
- flights table (one row per flight instance)
- positions table (time-series position data)

Usage:
    python3 backfill_snapshots.py [--dry-run] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
"""

import sqlite3
import sys
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from flight_db import FlightDatabase

def parse_args():
    parser = argparse.ArgumentParser(description='Backfill old snapshot data to new schema')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be migrated without actually doing it')
    parser.add_argument('--start-date', type=str,
                       help='Start date for migration (YYYY-MM-DD). Default: all data')
    parser.add_argument('--end-date', type=str,
                       help='End date for migration (YYYY-MM-DD). Default: all data')
    parser.add_argument('--db-path', type=str, default='flights.db',
                       help='Path to database file (default: flights.db)')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Number of positions to insert per batch (default: 1000)')
    return parser.parse_args()

def get_snapshots(conn, start_date=None, end_date=None):
    """Get all snapshots from the old table"""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    
    query = 'SELECT * FROM flight_snapshots WHERE 1=1'
    params = []
    
    if start_date:
        query += ' AND timestamp >= ?'
        params.append(start_date)
    
    if end_date:
        query += ' AND timestamp <= ?'
        params.append(end_date)
    
    query += ' ORDER BY icao, timestamp'
    
    cursor.execute(query, params)
    return cursor.fetchall()

def group_snapshots_by_flight(snapshots):
    """
    Group snapshots into flights.
    A flight is defined as consecutive snapshots with the same icao and callsign.
    If callsign changes or there's a gap > 30 minutes, it's a new flight.
    """
    flights = []
    current_flight = None
    
    for snapshot in snapshots:
        icao = snapshot['icao']
        callsign = snapshot['callsign'] or None
        timestamp = snapshot['timestamp']
        
        # Parse timestamp
        try:
            if '.' in timestamp:
                ts_dt = datetime.fromisoformat(timestamp)
            else:
                ts_dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
        except:
            print(f"⚠️  Warning: Could not parse timestamp {timestamp}, skipping")
            continue
        
        # Check if this starts a new flight
        if current_flight is None:
            # Start new flight
            current_flight = {
                'icao': icao,
                'callsign': callsign,
                'snapshots': [snapshot],
                'start_time': timestamp,
                'end_time': timestamp,
                'first_ts': ts_dt,
                'last_ts': ts_dt
            }
        else:
            # Check if same flight or new flight
            time_gap = (ts_dt - current_flight['last_ts']).total_seconds() / 60  # minutes
            
            if (current_flight['icao'] == icao and 
                current_flight['callsign'] == callsign and 
                time_gap <= 30):
                # Same flight - add to current
                current_flight['snapshots'].append(snapshot)
                current_flight['end_time'] = timestamp
                current_flight['last_ts'] = ts_dt
            else:
                # New flight - save current and start new
                flights.append(current_flight)
                current_flight = {
                    'icao': icao,
                    'callsign': callsign,
                    'snapshots': [snapshot],
                    'start_time': timestamp,
                    'end_time': timestamp,
                    'first_ts': ts_dt,
                    'last_ts': ts_dt
                }
    
    # Don't forget the last flight
    if current_flight:
        flights.append(current_flight)
    
    return flights

def extract_aircraft_info(snapshots):
    """Extract aircraft information from snapshots"""
    # Use the most complete snapshot (one with registration/model)
    best_snapshot = None
    for snapshot in snapshots:
        # sqlite3.Row supports direct indexing
        try:
            reg = snapshot['aircraft_registration']
            model = snapshot['aircraft_model']
            if reg or model:
                best_snapshot = snapshot
                break
        except (KeyError, IndexError):
            continue
    
    if not best_snapshot:
        best_snapshot = snapshots[0]
    
    # Access Row fields directly (returns None if key doesn't exist)
    def safe_get(row, key):
        try:
            return row[key]
        except (KeyError, IndexError):
            return None
    
    return {
        'registration': safe_get(best_snapshot, 'aircraft_registration'),
        'type': safe_get(best_snapshot, 'aircraft_type'),
        'model': safe_get(best_snapshot, 'aircraft_model'),
        'manufacturer': None  # Not in old schema
    }

def extract_flight_info(snapshots):
    """Extract flight information from snapshots"""
    # Helper function to safely get values from Row
    def safe_get(row, key):
        try:
            return row[key]
        except (KeyError, IndexError):
            return None
    
    # Use the most complete snapshot
    best_snapshot = None
    for snapshot in snapshots:
        origin = safe_get(snapshot, 'origin')
        dest = safe_get(snapshot, 'destination')
        if origin or dest:
            best_snapshot = snapshot
            break
    
    if not best_snapshot:
        best_snapshot = snapshots[0]
    
    # Access Row fields directly
    return {
        'origin': safe_get(best_snapshot, 'origin'),
        'destination': safe_get(best_snapshot, 'destination'),
        'origin_country': safe_get(best_snapshot, 'origin_country'),
        'destination_country': safe_get(best_snapshot, 'destination_country'),
        'airline_code': safe_get(best_snapshot, 'airline_code'),
        'airline_name': safe_get(best_snapshot, 'airline_name'),
        'status': safe_get(best_snapshot, 'status') or 'airborne'
    }

def backfill(db_path, start_date=None, end_date=None, dry_run=False, batch_size=1000):
    """Main backfill function"""
    print(f"🔄 Starting backfill migration...")
    print(f"   Database: {db_path}")
    print(f"   Start date: {start_date or 'all'}")
    print(f"   End date: {end_date or 'all'}")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Check if flight_snapshots table exists
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flight_snapshots'")
    if not cursor.fetchone():
        print("❌ Error: flight_snapshots table not found!")
        print("   This script migrates data from the old snapshot-based system.")
        print("   If you don't have old data, you don't need to run this.")
        return
    
    # Get snapshot count
    count_query = 'SELECT COUNT(*) FROM flight_snapshots'
    count_params = []
    if start_date:
        count_query += ' WHERE timestamp >= ?'
        count_params.append(start_date)
    if end_date:
        if start_date:
            count_query += ' AND timestamp <= ?'
        else:
            count_query += ' WHERE timestamp <= ?'
        count_params.append(end_date)
    
    cursor.execute(count_query, count_params)
    total_snapshots = cursor.fetchone()[0]
    
    if total_snapshots == 0:
        print("ℹ️  No snapshots found in the specified date range.")
        return
    
    print(f"📊 Found {total_snapshots:,} snapshots to process")
    print()
    
    # Get all snapshots
    print("📥 Loading snapshots from database...")
    snapshots = get_snapshots(conn, start_date, end_date)
    print(f"   Loaded {len(snapshots):,} snapshots")
    
    # Group into flights
    print("🔀 Grouping snapshots into flights...")
    flights = group_snapshots_by_flight(snapshots)
    print(f"   Identified {len(flights):,} flights")
    
    if dry_run:
        print()
        print("=" * 60)
        print("DRY RUN - No data will be written")
        print("=" * 60)
        print()
        
        # Show statistics
        aircraft_count = len(set(f['icao'] for f in flights))
        total_positions = sum(len(f['snapshots']) for f in flights)
        
        print(f"📈 Migration Summary:")
        print(f"   Aircraft: {aircraft_count:,} unique")
        print(f"   Flights: {len(flights):,}")
        print(f"   Positions: {total_positions:,}")
        print()
        
        # Show sample flights
        print("📋 Sample flights (first 5):")
        for i, flight in enumerate(flights[:5], 1):
            print(f"   {i}. ICAO: {flight['icao']}, Callsign: {flight['callsign'] or 'N/A'}, "
                  f"Snapshots: {len(flight['snapshots'])}, "
                  f"Duration: {flight['start_time'][:19]} to {flight['end_time'][:19]}")
        
        print()
        print("✅ Dry run complete. Run without --dry-run to perform migration.")
        return
    
    # Initialize FlightDatabase
    print()
    print("💾 Starting migration...")
    flight_db = FlightDatabase(db_path)
    
    # Statistics
    aircraft_created = 0
    aircraft_updated = 0
    flights_created = 0
    positions_inserted = 0
    
    # Process each flight
    for i, flight_data in enumerate(flights, 1):
        if i % 100 == 0:
            print(f"   Progress: {i}/{len(flights)} flights processed...")
        
        icao = flight_data['icao']
        snapshots = flight_data['snapshots']
        
        # Extract aircraft info
        aircraft_info = extract_aircraft_info(snapshots)
        
        # Upsert aircraft
        existing_aircraft = flight_db.get_aircraft(icao)
        if existing_aircraft:
            # Update if we have better info
            if aircraft_info['registration'] and not existing_aircraft.get('registration'):
                flight_db.upsert_aircraft(icao, aircraft_info)
                aircraft_updated += 1
        else:
            flight_db.upsert_aircraft(icao, aircraft_info)
            aircraft_created += 1
        
        # Extract flight info
        flight_info = extract_flight_info(snapshots)
        
        # Check if flight already exists (by icao, callsign, and start_time)
        # We'll create a new flight anyway since we can't easily match old flights
        # The new system will handle duplicates gracefully
        
        # Create flight
        flight_id = flight_db.start_flight(
            icao=icao,
            callsign=flight_data['callsign'],
            flight_info=flight_info
        )
        
        # Update flight start/end times (for historical data)
        # We need to directly update the database since start_flight uses current time
        update_conn = sqlite3.connect(db_path)
        update_cursor = update_conn.cursor()
        update_cursor.execute('''
            UPDATE flights 
            SET start_time = ?, end_time = ?
            WHERE id = ?
        ''', (flight_data['start_time'], flight_data['end_time'], flight_id))
        update_conn.commit()
        update_conn.close()
        
        # Mark flight as ended (historical data) - but end_time already set above
        # Just update status
        flight_db.end_flight(flight_id, 'landed')
        
        flights_created += 1
        
        # Insert positions in batches
        # Helper function to safely get values from Row
        def safe_get(row, key):
            try:
                return row[key]
            except (KeyError, IndexError):
                return None
        
        positions_batch = []
        for snapshot in snapshots:
            # Access Row fields directly (sqlite3.Row supports dict-style access)
            # Note: insert_position expects 'timestamp' not 'ts'
            position = {
                'timestamp': snapshot['timestamp'],
                'lat': safe_get(snapshot, 'lat'),
                'lon': safe_get(snapshot, 'lon'),
                'altitude': safe_get(snapshot, 'altitude'),
                'speed': safe_get(snapshot, 'speed'),
                'track': safe_get(snapshot, 'track'),
                'heading': safe_get(snapshot, 'heading'),
                'vertical_rate': safe_get(snapshot, 'vertical_rate'),
                'squawk': safe_get(snapshot, 'squawk'),
                'distance': safe_get(snapshot, 'distance')
            }
            positions_batch.append(position)
            
            if len(positions_batch) >= batch_size:
                for pos in positions_batch:
                    # insert_position expects (flight_id, position_data_dict)
                    flight_db.insert_position(flight_id, pos)
                    positions_inserted += 1
                positions_batch = []
        
        # Insert remaining positions
        for pos in positions_batch:
            # insert_position expects (flight_id, position_data_dict)
            flight_db.insert_position(flight_id, pos)
            positions_inserted += 1
    
    print()
    print("=" * 60)
    print("✅ Migration Complete!")
    print("=" * 60)
    print(f"📊 Statistics:")
    print(f"   Aircraft created: {aircraft_created:,}")
    print(f"   Aircraft updated: {aircraft_updated:,}")
    print(f"   Flights created: {flights_created:,}")
    print(f"   Positions inserted: {positions_inserted:,}")
    print()
    print("💡 Tip: Run 'python3 inspect_flight_db.py' to verify the migration")

if __name__ == '__main__':
    args = parse_args()
    
    # Validate dates
    start_date = None
    end_date = None
    
    if args.start_date:
        try:
            datetime.strptime(args.start_date, '%Y-%m-%d')
            start_date = args.start_date
        except ValueError:
            print(f"❌ Error: Invalid start date format: {args.start_date}")
            print("   Use YYYY-MM-DD format")
            sys.exit(1)
    
    if args.end_date:
        try:
            datetime.strptime(args.end_date, '%Y-%m-%d')
            end_date = args.end_date
        except ValueError:
            print(f"❌ Error: Invalid end date format: {args.end_date}")
            print("   Use YYYY-MM-DD format")
            sys.exit(1)
    
    try:
        backfill(
            db_path=args.db_path,
            start_date=start_date,
            end_date=end_date,
            dry_run=args.dry_run,
            batch_size=args.batch_size
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

