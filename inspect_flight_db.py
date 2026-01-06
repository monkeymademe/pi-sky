#!/usr/bin/env python3
"""
Flight Database Inspector
Quick tool to inspect the new flight-centric database schema
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

def inspect_database(db_path='flights.db'):
    """Inspect the flight database and show statistics"""
    
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("FLIGHT DATABASE INSPECTOR")
    print("=" * 80)
    print()
    
    # Check which tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"📋 Tables: {', '.join(tables)}")
    print()
    
    # New schema stats
    if 'aircraft' in tables:
        print("✈️  AIRCRAFT")
        print("-" * 80)
        cursor.execute("SELECT COUNT(*) FROM aircraft")
        aircraft_count = cursor.fetchone()[0]
        print(f"   Total aircraft: {aircraft_count}")
        
        if aircraft_count > 0:
            cursor.execute("""
                SELECT icao, registration, type, model, first_seen_at, last_seen_at
                FROM aircraft
                ORDER BY last_seen_at DESC
                LIMIT 5
            """)
            print("\n   Recent aircraft:")
            for row in cursor.fetchall():
                reg = row['registration'] or 'Unknown'
                model = row['model'] or 'Unknown'
                print(f"   • {row['icao']} - {reg} ({model})")
                print(f"     First seen: {row['first_seen_at']}")
                print(f"     Last seen:  {row['last_seen_at']}")
        print()
    
    if 'flights' in tables:
        print("🛫 FLIGHTS")
        print("-" * 80)
        cursor.execute("SELECT COUNT(*) FROM flights")
        flights_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM flights WHERE end_time IS NULL")
        active_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM flights WHERE end_time IS NOT NULL")
        ended_count = cursor.fetchone()[0]
        
        print(f"   Total flights: {flights_count}")
        print(f"   Active flights: {active_count}")
        print(f"   Ended flights: {ended_count}")
        
        if active_count > 0:
            print("\n   Active flights:")
            cursor.execute("""
                SELECT f.id, f.callsign, f.aircraft_icao, f.origin, f.destination,
                       f.start_time, f.status, a.registration, a.model
                FROM flights f
                LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
                WHERE f.end_time IS NULL
                ORDER BY f.start_time DESC
                LIMIT 10
            """)
            for row in cursor.fetchall():
                callsign = row['callsign'] or 'Unidentified'
                route = f"{row['origin'] or '???'} → {row['destination'] or '???'}"
                reg = row['registration'] or 'Unknown'
                model = row['model'] or 'Unknown'
                print(f"   • Flight #{row['id']}: {callsign} ({row['aircraft_icao']})")
                print(f"     Route: {route}")
                print(f"     Aircraft: {reg} ({model})")
                print(f"     Started: {row['start_time']}")
                print(f"     Status: {row['status']}")
        
        if flights_count > 0:
            print("\n   Recent flights (last 5):")
            cursor.execute("""
                SELECT f.id, f.callsign, f.aircraft_icao, f.origin, f.destination,
                       f.start_time, f.end_time, f.status, a.registration
                FROM flights f
                LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
                ORDER BY f.start_time DESC
                LIMIT 5
            """)
            for row in cursor.fetchall():
                callsign = row['callsign'] or 'Unidentified'
                route = f"{row['origin'] or '???'} → {row['destination'] or '???'}"
                reg = row['registration'] or 'Unknown'
                status = '✓ Active' if not row['end_time'] else f"✓ Ended ({row['status']})"
                print(f"   • Flight #{row['id']}: {callsign} ({row['aircraft_icao']}) - {reg}")
                print(f"     Route: {route}")
                print(f"     Started: {row['start_time']}")
                if row['end_time']:
                    print(f"     Ended: {row['end_time']}")
                print(f"     {status}")
        print()
    
    if 'positions' in tables:
        print("📍 POSITIONS")
        print("-" * 80)
        cursor.execute("SELECT COUNT(*) FROM positions")
        positions_count = cursor.fetchone()[0]
        print(f"   Total positions: {positions_count:,}")
        
        if positions_count > 0:
            cursor.execute("""
                SELECT MIN(ts) as first_pos, MAX(ts) as last_pos
                FROM positions
            """)
            row = cursor.fetchone()
            print(f"   First position: {row['first_pos']}")
            print(f"   Last position:  {row['last_pos']}")
            
            # Positions per flight
            cursor.execute("""
                SELECT f.id, f.callsign, f.aircraft_icao, COUNT(p.id) as pos_count
                FROM flights f
                LEFT JOIN positions p ON f.id = p.flight_id
                WHERE f.end_time IS NULL
                GROUP BY f.id
                ORDER BY pos_count DESC
                LIMIT 5
            """)
            print("\n   Positions per active flight:")
            for row in cursor.fetchall():
                callsign = row['callsign'] or 'Unidentified'
                print(f"   • Flight #{row['id']} ({callsign}): {row['pos_count']:,} positions")
        print()
    
    # Old schema stats (for comparison)
    if 'flight_snapshots' in tables:
        print("📸 LEGACY SNAPSHOTS (old schema)")
        print("-" * 80)
        cursor.execute("SELECT COUNT(*) FROM flight_snapshots")
        snapshots_count = cursor.fetchone()[0]
        print(f"   Total snapshots: {snapshots_count:,}")
        
        if snapshots_count > 0:
            cursor.execute("""
                SELECT MIN(timestamp) as first_snap, MAX(timestamp) as last_snap
                FROM flight_snapshots
            """)
            row = cursor.fetchone()
            print(f"   First snapshot: {row['first_snap']}")
            print(f"   Last snapshot:  {row['last_snap']}")
        print()
    
    # Database size
    db_size = Path(db_path).stat().st_size
    print(f"💾 Database size: {db_size / (1024*1024):.2f} MB")
    print()
    
    conn.close()

def show_flight_details(db_path, flight_id):
    """Show detailed information about a specific flight"""
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT f.*, a.registration, a.type, a.model, a.manufacturer
        FROM flights f
        LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
        WHERE f.id = ?
    """, (flight_id,))
    
    flight = cursor.fetchone()
    if not flight:
        print(f"❌ Flight #{flight_id} not found")
        conn.close()
        return
    
    print("=" * 80)
    print(f"FLIGHT #{flight['id']} DETAILS")
    print("=" * 80)
    print()
    
    callsign = flight['callsign'] or 'Unidentified'
    print(f"Callsign: {callsign}")
    print(f"Aircraft ICAO: {flight['aircraft_icao']}")
    print(f"Registration: {flight['registration'] or 'Unknown'}")
    print(f"Aircraft Type: {flight['type'] or 'Unknown'}")
    print(f"Aircraft Model: {flight['model'] or 'Unknown'}")
    print()
    
    route = f"{flight['origin'] or '???'} → {flight['destination'] or '???'}"
    print(f"Route: {route}")
    if flight['origin_country'] or flight['destination_country']:
        print(f"Countries: {flight['origin_country'] or '???'} → {flight['destination_country'] or '???'}")
    print()
    
    if flight['airline_code']:
        print(f"Airline: {flight['airline_name'] or 'Unknown'} ({flight['airline_code']})")
        print()
    
    print(f"Start time: {flight['start_time']}")
    if flight['end_time']:
        print(f"End time: {flight['end_time']}")
    print(f"Status: {flight['status']}")
    print()
    
    # Position count
    cursor.execute("SELECT COUNT(*) FROM positions WHERE flight_id = ?", (flight_id,))
    pos_count = cursor.fetchone()[0]
    print(f"Position records: {pos_count:,}")
    
    if pos_count > 0:
        cursor.execute("""
            SELECT MIN(ts) as first_pos, MAX(ts) as last_pos
            FROM positions WHERE flight_id = ?
        """, (flight_id,))
        row = cursor.fetchone()
        print(f"First position: {row['first_pos']}")
        print(f"Last position: {row['last_pos']}")
        
        # Show recent positions
        cursor.execute("""
            SELECT ts, lat, lon, altitude, speed, track, heading
            FROM positions
            WHERE flight_id = ?
            ORDER BY ts DESC
            LIMIT 5
        """, (flight_id,))
        
        print("\nRecent positions:")
        for row in cursor.fetchall():
            print(f"  {row['ts']}")
            print(f"    Position: {row['lat']:.5f}, {row['lon']:.5f}")
            print(f"    Altitude: {row['altitude']} ft, Speed: {row['speed']} kts")
            print(f"    Track: {row['track']}°, Heading: {row['heading']}°")
    
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == '--flight' and len(sys.argv) > 2:
            show_flight_details('flights.db', int(sys.argv[2]))
        else:
            inspect_database(sys.argv[1])
    else:
        inspect_database()

