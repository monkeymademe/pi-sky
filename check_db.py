#!/usr/bin/env python3
"""
Quick script to check what's in the flight database
"""
import sqlite3
import json
from datetime import datetime

db_path = 'flights.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flight_snapshots'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        print("❌ Table 'flight_snapshots' does not exist!")
        conn.close()
        exit(1)
    
    # Count total snapshots
    cursor.execute("SELECT COUNT(*) FROM flight_snapshots")
    total_snapshots = cursor.fetchone()[0]
    print(f"📊 Total snapshots: {total_snapshots}")
    
    # Count snapshots with flights (non-null ICAO)
    cursor.execute("SELECT COUNT(DISTINCT timestamp) FROM flight_snapshots WHERE icao IS NOT NULL")
    snapshots_with_flights = cursor.fetchone()[0]
    print(f"📊 Snapshots with flight data: {snapshots_with_flights}")
    
    # Count total flight records
    cursor.execute("SELECT COUNT(*) FROM flight_snapshots WHERE icao IS NOT NULL")
    total_flights = cursor.fetchone()[0]
    print(f"📊 Total flight records: {total_flights}")
    
    # Count flights with position
    cursor.execute("SELECT COUNT(*) FROM flight_snapshots WHERE lat IS NOT NULL AND lon IS NOT NULL")
    flights_with_pos = cursor.fetchone()[0]
    print(f"📊 Flights with position data: {flights_with_pos}")
    
    # Get date range
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM flight_snapshots")
    min_ts, max_ts = cursor.fetchone()
    print(f"📊 Date range: {min_ts} to {max_ts}")
    
    # Get sample timestamps with flight counts
    cursor.execute('''
        SELECT timestamp, COUNT(*) as count
        FROM flight_snapshots
        WHERE icao IS NOT NULL
        GROUP BY timestamp
        ORDER BY timestamp
        LIMIT 10
    ''')
    samples = cursor.fetchall()
    
    if samples:
        print(f"\n📋 Sample timestamps with flights:")
        for ts, count in samples:
            # Check how many have position
            cursor.execute('''
                SELECT COUNT(*) FROM flight_snapshots
                WHERE timestamp = ? AND lat IS NOT NULL AND lon IS NOT NULL
            ''', (ts,))
            with_pos = cursor.fetchone()[0]
            print(f"   {ts}: {count} flights ({with_pos} with position)")
    else:
        print("\n⚠️  No timestamps found with flight data!")
    
    # Get a sample flight record WITH position
    cursor.execute('''
        SELECT * FROM flight_snapshots
        WHERE icao IS NOT NULL AND lat IS NOT NULL AND lon IS NOT NULL
        LIMIT 1
    ''')
    sample = cursor.fetchone()
    
    if sample:
        # Get column names
        cursor.execute("PRAGMA table_info(flight_snapshots)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"\n📋 Sample flight record WITH position:")
        flight_dict = dict(zip(columns, sample))
        for key, value in flight_dict.items():
            if value is not None:
                print(f"   {key}: {value}")
    else:
        print("\n⚠️  No flight records with position found!")
    
    # Get a sample flight record WITHOUT position
    cursor.execute('''
        SELECT * FROM flight_snapshots
        WHERE icao IS NOT NULL AND (lat IS NULL OR lon IS NULL)
        LIMIT 1
    ''')
    sample_no_pos = cursor.fetchone()
    
    if sample_no_pos:
        print(f"\n📋 Sample flight record WITHOUT position:")
        flight_dict = dict(zip(columns, sample_no_pos))
        for key, value in flight_dict.items():
            if value is not None:
                print(f"   {key}: {value}")
    
    # Check specific timestamp that should have data
    test_timestamp = '2025-12-17T20:31:11'
    cursor.execute('''
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN lat IS NOT NULL AND lon IS NOT NULL THEN 1 END) as with_pos
        FROM flight_snapshots
        WHERE timestamp LIKE ?
    ''', (f'{test_timestamp}%',))
    result = cursor.fetchone()
    print(f"\n📊 Timestamp {test_timestamp}: {result[0]} total flights, {result[1]} with position")
    
    # Get actual flights for that timestamp
    cursor.execute('''
        SELECT icao, callsign, lat, lon, timestamp
        FROM flight_snapshots
        WHERE timestamp LIKE ?
        LIMIT 5
    ''', (f'{test_timestamp}%',))
    flights = cursor.fetchall()
    print(f"\n📋 Flights at {test_timestamp}:")
    for icao, callsign, lat, lon, ts in flights:
        has_pos = "✅" if lat is not None and lon is not None else "❌"
        print(f"   {has_pos} {callsign or 'Unidentified'} ({icao}): lat={lat}, lon={lon}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

