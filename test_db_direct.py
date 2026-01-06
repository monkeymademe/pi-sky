#!/usr/bin/env python3
"""
Direct database test - bypasses the API
"""

import sqlite3
import sys
import time

def test_database():
    db_path = 'flights.db'
    
    print("=" * 60)
    print("Testing Database Directly")
    print("=" * 60)
    print(f"Database: {db_path}")
    print()
    
    try:
        print("1. Connecting to database...")
        start = time.time()
        conn = sqlite3.connect(db_path, timeout=5.0)
        elapsed = time.time() - start
        print(f"   ✓ Connected in {elapsed:.3f} seconds")
        
        print("\n2. Testing simple query...")
        cursor = conn.cursor()
        
        start = time.time()
        cursor.execute("SELECT COUNT(*) FROM flights")
        count = cursor.fetchone()[0]
        elapsed = time.time() - start
        print(f"   ✓ Query completed in {elapsed:.3f} seconds")
        print(f"   Total flights: {count}")
        
        if count == 0:
            print("\n   ⚠️  No flights in database!")
            conn.close()
            return True
        
        print("\n3. Testing flights query with JOIN...")
        start = time.time()
        cursor.execute('''
            SELECT f.id, f.callsign, f.aircraft_icao, a.registration
            FROM flights f
            LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
            ORDER BY f.start_time DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        elapsed = time.time() - start
        print(f"   ✓ Query completed in {elapsed:.3f} seconds")
        
        if row:
            print(f"   First flight: id={row[0]}, callsign={row[1]}, icao={row[2]}, reg={row[3]}")
        else:
            print("   No flights returned")
        
        print("\n4. Testing full query (like API uses)...")
        start = time.time()
        cursor.execute('''
            SELECT f.*, a.registration, a.type, a.model, a.manufacturer
            FROM flights f
            LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
            ORDER BY f.start_time DESC
            LIMIT 1
        ''')
        rows = cursor.fetchall()
        elapsed = time.time() - start
        print(f"   ✓ Query completed in {elapsed:.3f} seconds")
        print(f"   Rows returned: {len(rows)}")
        
        if elapsed > 1:
            print(f"   ⚠️  WARNING: Query took {elapsed:.2f} seconds (slow!)")
        
        conn.close()
        print("\n   ✓ Database test completed successfully")
        return True
        
    except sqlite3.OperationalError as e:
        print(f"\n   ✗ Database error: {e}")
        if "locked" in str(e).lower():
            print("   → Database is locked by another process")
            print("   → Stop the server and try again")
        return False
    except Exception as e:
        print(f"\n   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_database()
    print()
    print("=" * 60)
    if success:
        print("✅ Database is accessible")
    else:
        print("❌ Database test failed")
    print("=" * 60)
    sys.exit(0 if success else 1)

