#!/usr/bin/env python3
"""
Flight Database Module
SQLite database for storing flight data snapshots for replay functionality
"""

import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path

class FlightDatabase:
    """SQLite database for storing flight data"""
    
    def __init__(self, db_path='flights.db'):
        """
        Initialize the flight database
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create flight_snapshots table
            # Stores periodic snapshots of all detected flights
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS flight_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    icao TEXT NOT NULL,
                    callsign TEXT,
                    lat REAL,
                    lon REAL,
                    altitude INTEGER,
                    speed REAL,
                    track REAL,
                    heading REAL,
                    vertical_rate INTEGER,
                    squawk TEXT,
                    distance REAL,
                    origin TEXT,
                    destination TEXT,
                    origin_country TEXT,
                    destination_country TEXT,
                    aircraft_model TEXT,
                    aircraft_type TEXT,
                    aircraft_registration TEXT,
                    airline_code TEXT,
                    airline_name TEXT,
                    status TEXT,
                    unidentified INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for efficient queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON flight_snapshots(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_icao ON flight_snapshots(icao)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_icao_timestamp ON flight_snapshots(icao, timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_callsign ON flight_snapshots(callsign)
            ''')
            
            # Create flight_events table
            # Stores significant events (new flight detected, route found, etc.)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS flight_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    icao TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_event_timestamp ON flight_events(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_event_icao ON flight_events(icao)
            ''')
            
            # Enable WAL mode for better concurrency (allows reads during writes)
            cursor.execute('PRAGMA journal_mode=WAL')
            wal_result = cursor.fetchone()
            print(f"   Database journal mode: {wal_result[0] if wal_result else 'unknown'}")
            
            # Initialize new flight-centric schema
            self._init_new_schema(conn, cursor)
            
            conn.commit()
            conn.close()
    
    def save_snapshot(self, flights, timestamp=None):
        """
        Save a snapshot of all current flights
        
        Args:
            flights: List of flight dictionaries
            timestamp: Optional timestamp (defaults to current time)
        """
        if timestamp is None:
            # Use ISO format with microseconds for precision (we'll query with tolerance)
            timestamp = datetime.now().isoformat()
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for flight in flights:
                cursor.execute('''
                    INSERT INTO flight_snapshots (
                        timestamp, icao, callsign, lat, lon, altitude, speed, track,
                        heading, vertical_rate, squawk, distance, origin, destination,
                        origin_country, destination_country, aircraft_model, aircraft_type,
                        aircraft_registration, airline_code, airline_name, status, unidentified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    timestamp,
                    flight.get('icao'),
                    flight.get('callsign'),
                    flight.get('lat'),
                    flight.get('lon'),
                    flight.get('altitude'),
                    flight.get('speed'),
                    flight.get('track'),
                    flight.get('heading'),
                    flight.get('vertical_rate'),
                    flight.get('squawk'),
                    flight.get('distance'),
                    flight.get('origin'),
                    flight.get('destination'),
                    flight.get('origin_country'),
                    flight.get('destination_country'),
                    flight.get('aircraft_model'),
                    flight.get('aircraft_type'),
                    flight.get('aircraft_registration'),
                    flight.get('airline_code'),
                    flight.get('airline_name'),
                    flight.get('status'),
                    1 if flight.get('unidentified') else 0
                ))
            
            conn.commit()
            conn.close()
    
    def save_event(self, icao, event_type, event_data=None, timestamp=None):
        """
        Save a flight event
        
        Args:
            icao: Aircraft ICAO code
            event_type: Type of event (e.g., 'new_flight', 'route_found', 'aircraft_info_found')
            event_data: Optional JSON-serializable data
            timestamp: Optional timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        event_data_json = json.dumps(event_data) if event_data else None
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO flight_events (timestamp, icao, event_type, event_data)
                VALUES (?, ?, ?, ?)
            ''', (timestamp, icao, event_type, event_data_json))
            
            conn.commit()
            conn.close()
    
    def get_flights_by_time_range(self, start_time, end_time):
        """
        Get all flight snapshots within a time range
        
        Args:
            start_time: Start timestamp (ISO format string or datetime)
            end_time: End timestamp (ISO format string or datetime)
        
        Returns:
            List of flight snapshot dictionaries
        """
        if isinstance(start_time, datetime):
            start_time = start_time.isoformat()
        if isinstance(end_time, datetime):
            end_time = end_time.isoformat()
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM flight_snapshots
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp, icao
            ''', (start_time, end_time))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
    
    def get_flight_history(self, icao, start_time=None, end_time=None):
        """
        Get history for a specific flight
        
        Args:
            icao: Aircraft ICAO code
            start_time: Optional start timestamp
            end_time: Optional end timestamp
        
        Returns:
            List of flight snapshot dictionaries
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if start_time and end_time:
                if isinstance(start_time, datetime):
                    start_time = start_time.isoformat()
                if isinstance(end_time, datetime):
                    end_time = end_time.isoformat()
                cursor.execute('''
                    SELECT * FROM flight_snapshots
                    WHERE icao = ? AND timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp
                ''', (icao, start_time, end_time))
            else:
                cursor.execute('''
                    SELECT * FROM flight_snapshots
                    WHERE icao = ?
                    ORDER BY timestamp
                ''', (icao,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
    
    def get_flights_at_time(self, timestamp, tolerance_seconds=5):
        """
        Get all flights at a specific timestamp (or closest match)
        
        Args:
            timestamp: Timestamp (ISO format string or datetime)
            tolerance_seconds: Maximum seconds difference to accept (default: 5)
        
        Returns:
            List of flight snapshot dictionaries
        """
        if isinstance(timestamp, datetime):
            timestamp = timestamp.strftime('%Y-%m-%dT%H:%M:%S')
        elif isinstance(timestamp, str):
            # Normalize timestamp format - remove extra colons, microseconds, timezone
            # Handle malformed timestamps like "2025-12-17T20:34:00:00"
            if '::' in timestamp:
                # Fix double colon issue
                timestamp = timestamp.replace('::', ':')
            
            # Parse and normalize
            try:
                # Try to parse the timestamp
                if '.' in timestamp or '+' in timestamp or timestamp.endswith('Z'):
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                else:
                    # Handle format without timezone
                    dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
                timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S')
            except ValueError as e:
                # If parsing fails, try to clean up the string
                # Remove microseconds if present
                if '.' in timestamp:
                    timestamp = timestamp.split('.')[0]
                # Remove timezone if present
                if '+' in timestamp:
                    timestamp = timestamp.split('+')[0]
                if 'Z' in timestamp:
                    timestamp = timestamp.replace('Z', '')
                # Remove any extra colons at the end
                while timestamp.endswith(':'):
                    timestamp = timestamp[:-1]
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # First try exact match (but database timestamps may have microseconds)
            # So we'll use a range query instead
            cursor.execute('''
                SELECT * FROM flight_snapshots
                WHERE ABS(JULIANDAY(timestamp) - JULIANDAY(?)) * 86400 <= ?
                ORDER BY ABS(JULIANDAY(timestamp) - JULIANDAY(?)), icao
            ''', (timestamp, tolerance_seconds, timestamp))
            rows = cursor.fetchall()
            
            # Debug: show what we found
            if rows:
                actual_timestamp = rows[0]['timestamp']
                try:
                    # Parse timestamps (handle microseconds)
                    query_dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
                    if '.' in actual_timestamp:
                        actual_dt = datetime.fromisoformat(actual_timestamp)
                    else:
                        actual_dt = datetime.strptime(actual_timestamp, '%Y-%m-%dT%H:%M:%S')
                    time_diff = abs((actual_dt - query_dt).total_seconds())
                    if time_diff > 0.1:  # Only log if difference is significant
                        print(f"   ℹ️  Query: {timestamp}, Found: {actual_timestamp} (diff: {time_diff:.1f}s)")
                except Exception as e:
                    print(f"   ℹ️  Found {len(rows)} flights (timestamp comparison failed: {e})")
            else:
                print(f"   ⚠️  No flights found within {tolerance_seconds}s of {timestamp}")
            
            conn.close()
            
            return [dict(row) for row in rows]
    
    def get_unique_flights(self, start_time=None, end_time=None):
        """
        Get list of unique flights (ICAO codes) in a time range
        
        Args:
            start_time: Optional start timestamp
            end_time: Optional end timestamp
        
        Returns:
            List of unique ICAO codes
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if start_time and end_time:
                if isinstance(start_time, datetime):
                    start_time = start_time.isoformat()
                if isinstance(end_time, datetime):
                    end_time = end_time.isoformat()
                cursor.execute('''
                    SELECT DISTINCT icao FROM flight_snapshots
                    WHERE timestamp >= ? AND timestamp <= ?
                    ORDER BY icao
                ''', (start_time, end_time))
            else:
                cursor.execute('''
                    SELECT DISTINCT icao FROM flight_snapshots
                    ORDER BY icao
                ''')
            
            icaos = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            return icaos
    
    def cleanup_old_data(self, days_to_keep=7):
        """
        Delete data older than specified days
        
        Args:
            days_to_keep: Number of days of data to keep (default: 7)
        """
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.isoformat()
        
        print(f"🧹 Starting database cleanup: Keeping data from last {days_to_keep} days (cutoff: {cutoff_str})")
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get counts before deletion for logging (all tables)
            cursor.execute('SELECT COUNT(*) FROM flight_snapshots WHERE timestamp < ?', (cutoff_str,))
            snapshots_to_delete = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM flight_events WHERE timestamp < ?', (cutoff_str,))
            events_to_delete = cursor.fetchone()[0]
            
            # Check new tables
            cursor.execute('SELECT COUNT(*) FROM positions WHERE ts < ?', (cutoff_str,))
            positions_to_delete = cursor.fetchone()[0]
            
            # Find flights that ended before cutoff (or started before cutoff if still active but old)
            cursor.execute('''
                SELECT COUNT(*) FROM flights 
                WHERE (end_time IS NOT NULL AND end_time < ?) 
                   OR (end_time IS NULL AND start_time < ?)
            ''', (cutoff_str, cutoff_str))
            flights_to_delete = cursor.fetchone()[0]
            
            # Find aircraft not seen recently (only count those not referenced by flights)
            cursor.execute('''
                SELECT COUNT(*) FROM aircraft 
                WHERE last_seen_at < ?
                  AND icao NOT IN (SELECT DISTINCT aircraft_icao FROM flights WHERE aircraft_icao IS NOT NULL)
            ''', (cutoff_str,))
            aircraft_to_delete = cursor.fetchone()[0]
            
            total_to_delete = snapshots_to_delete + events_to_delete + positions_to_delete + flights_to_delete + aircraft_to_delete
            
            if total_to_delete == 0:
                conn.close()
                print(f"   No data older than {days_to_keep} days to delete")
                return 0, 0
            
            # Get database size before cleanup
            db_size_before = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
            
            # Delete old positions first (they reference flights via foreign key)
            if positions_to_delete > 0:
                cursor.execute('''
                    DELETE FROM positions
                    WHERE ts < ?
                ''', (cutoff_str,))
                positions_deleted = cursor.rowcount
                print(f"   Deleted {positions_deleted} old positions")
            else:
                positions_deleted = 0
            
            # Delete old flights (positions already deleted, so safe to delete flights)
            if flights_to_delete > 0:
                # Delete flights that ended before cutoff, or started before cutoff if still active
                cursor.execute('''
                    DELETE FROM flights 
                    WHERE (end_time IS NOT NULL AND end_time < ?) 
                       OR (end_time IS NULL AND start_time < ?)
                ''', (cutoff_str, cutoff_str))
                flights_deleted = cursor.rowcount
                print(f"   Deleted {flights_deleted} old flights")
            else:
                flights_deleted = 0
            
            # Delete old aircraft (only if not referenced by any remaining flights)
            if aircraft_to_delete > 0:
                cursor.execute('''
                    DELETE FROM aircraft 
                    WHERE last_seen_at < ?
                      AND icao NOT IN (SELECT DISTINCT aircraft_icao FROM flights WHERE aircraft_icao IS NOT NULL)
                ''', (cutoff_str,))
                aircraft_deleted = cursor.rowcount
                print(f"   Deleted {aircraft_deleted} old aircraft")
            else:
                aircraft_deleted = 0
            
            # Delete old snapshots (legacy table)
            if snapshots_to_delete > 0:
                cursor.execute('''
                    DELETE FROM flight_snapshots
                    WHERE timestamp < ?
                ''', (cutoff_str,))
                snapshots_deleted = cursor.rowcount
            else:
                snapshots_deleted = 0
            
            # Delete old events (legacy table)
            if events_to_delete > 0:
                cursor.execute('''
                    DELETE FROM flight_events
                    WHERE timestamp < ?
                ''', (cutoff_str,))
                events_deleted = cursor.rowcount
            else:
                events_deleted = 0
            
            conn.commit()
            
            # Vacuum database to reclaim space (only if we deleted something)
            if total_to_delete > 0:
                print(f"   Vacuuming database to reclaim disk space...")
                cursor.execute('VACUUM')
                conn.commit()
            
            conn.close()
            
            # Get database size after cleanup (need to wait a moment for filesystem to update)
            import time
            time.sleep(0.2)  # Brief pause for filesystem to update after VACUUM
            db_size_after = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
            size_reclaimed_mb = round((db_size_before - db_size_after) / (1024 * 1024), 2)
            
            print(f"   ✅ Cleanup complete:")
            print(f"      • Deleted {positions_deleted} positions")
            print(f"      • Deleted {flights_deleted} flights")
            print(f"      • Deleted {aircraft_deleted} aircraft")
            print(f"      • Deleted {snapshots_deleted} snapshots (legacy)")
            print(f"      • Deleted {events_deleted} events (legacy)")
            if size_reclaimed_mb > 0:
                print(f"   💾 Reclaimed {size_reclaimed_mb} MB of disk space ({db_size_before / (1024*1024):.2f} MB → {db_size_after / (1024*1024):.2f} MB)")
            
            return snapshots_deleted, events_deleted
    
    def get_database_stats(self):
        """
        Get database statistics
        
        Returns:
            Dictionary with database statistics
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count snapshots
            cursor.execute('SELECT COUNT(*) FROM flight_snapshots')
            snapshot_count = cursor.fetchone()[0]
            
            # Count events
            cursor.execute('SELECT COUNT(*) FROM flight_events')
            event_count = cursor.fetchone()[0]
            
            # Get date range
            cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM flight_snapshots')
            date_range = cursor.fetchone()
            min_date = date_range[0] if date_range[0] else None
            max_date = date_range[1] if date_range[1] else None
            
            # Get unique flights
            cursor.execute('SELECT COUNT(DISTINCT icao) FROM flight_snapshots')
            unique_flights = cursor.fetchone()[0]
            
            # Get database size
            db_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
            
            conn.close()
            
            return {
                'snapshot_count': snapshot_count,
                'event_count': event_count,
                'unique_flights': unique_flights,
                'min_date': min_date,
                'max_date': max_date,
                'database_size_mb': round(db_size / (1024 * 1024), 2)
            }
    
    def _init_new_schema(self, conn, cursor):
        """Initialize the new flight-centric schema"""
        
        # Aircraft table - one row per ICAO24 (unique per aircraft/transponder)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aircraft (
                icao TEXT PRIMARY KEY,
                registration TEXT,
                type TEXT,
                model TEXT,
                manufacturer TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT
            )
        ''')
        
        # Flights table - one row per flight instance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aircraft_icao TEXT NOT NULL REFERENCES aircraft(icao),
                callsign TEXT,
                origin TEXT,
                destination TEXT,
                origin_country TEXT,
                destination_country TEXT,
                airline_code TEXT,
                airline_name TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_flights_aircraft ON flights(aircraft_icao)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_flights_callsign ON flights(callsign)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_flights_time ON flights(start_time, end_time)')
        
        # Positions table - time-series data for each flight
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_id INTEGER NOT NULL REFERENCES flights(id),
                ts TEXT NOT NULL,
                lat REAL,
                lon REAL,
                altitude INTEGER,
                speed REAL,
                track REAL,
                heading REAL,
                vertical_rate INTEGER,
                squawk TEXT,
                distance REAL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_flight_ts ON positions(flight_id, ts)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_ts ON positions(ts)')
        
        # Update flight_events table to support flight_id (keep backward compatibility)
        # Note: We already have flight_events table, so we just add an index for flight_id if needed
        # The old events use icao, new ones can use flight_id
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_flight_id ON flight_events(
                CAST(json_extract(event_data, '$.flight_id') AS INTEGER)
            )
        ''')
    
    def upsert_aircraft(self, icao, aircraft_info=None):
        """
        Insert or update aircraft record
        
        Args:
            icao: ICAO24 hex code
            aircraft_info: dict with registration, type, model, manufacturer
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Insert or update last_seen_at
            cursor.execute('''
                INSERT INTO aircraft (icao, first_seen_at, last_seen_at)
                VALUES (?, ?, ?)
                ON CONFLICT(icao) DO UPDATE SET last_seen_at = ?
            ''', (icao, now, now, now))
            
            # Update additional fields if provided
            if aircraft_info:
                cursor.execute('''
                    UPDATE aircraft 
                    SET registration = COALESCE(?, registration),
                        type = COALESCE(?, type),
                        model = COALESCE(?, model),
                        manufacturer = COALESCE(?, manufacturer)
                    WHERE icao = ?
                ''', (
                    aircraft_info.get('registration'),
                    aircraft_info.get('type'),
                    aircraft_info.get('model'),
                    aircraft_info.get('manufacturer'),
                    icao
                ))
            
            conn.commit()
            conn.close()
    
    def get_active_flight(self, icao):
        """
        Get the currently active flight for an aircraft
        
        Args:
            icao: ICAO24 hex code
            
        Returns:
            dict with flight info or None
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM flights 
                WHERE aircraft_icao = ? AND end_time IS NULL
                ORDER BY start_time DESC
                LIMIT 1
            ''', (icao,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
    
    def start_flight(self, icao, callsign, flight_info=None):
        """
        Start a new flight record
        
        Args:
            icao: ICAO24 hex code
            callsign: Flight callsign (can be None for unidentified)
            flight_info: dict with origin, destination, airline_code, etc.
            
        Returns:
            flight_id: ID of the new flight record
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            info = flight_info or {}
            
            cursor.execute('''
                INSERT INTO flights (
                    aircraft_icao, callsign, origin, destination,
                    origin_country, destination_country,
                    airline_code, airline_name,
                    start_time, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                icao,
                callsign,
                info.get('origin'),
                info.get('destination'),
                info.get('origin_country'),
                info.get('destination_country'),
                info.get('airline_code'),
                info.get('airline_name'),
                now,
                'airborne'
            ))
            
            flight_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return flight_id
    
    def end_flight(self, flight_id, status='landed'):
        """
        Mark a flight as ended
        
        Args:
            flight_id: ID of the flight to end
            status: Final status (landed, unknown, etc.)
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE flights 
                SET end_time = ?, status = ?
                WHERE id = ?
            ''', (now, status, flight_id))
            
            conn.commit()
            conn.close()
    
    def update_flight_info(self, flight_id, flight_info):
        """
        Update flight information (origin, destination, etc.)
        
        Args:
            flight_id: ID of the flight
            flight_info: dict with fields to update
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE flights 
                SET origin = COALESCE(?, origin),
                    destination = COALESCE(?, destination),
                    origin_country = COALESCE(?, origin_country),
                    destination_country = COALESCE(?, destination_country),
                    airline_code = COALESCE(?, airline_code),
                    airline_name = COALESCE(?, airline_name)
                WHERE id = ?
            ''', (
                flight_info.get('origin'),
                flight_info.get('destination'),
                flight_info.get('origin_country'),
                flight_info.get('destination_country'),
                flight_info.get('airline_code'),
                flight_info.get('airline_name'),
                flight_id
            ))
            
            conn.commit()
            conn.close()
    
    def insert_position(self, flight_id, position_data):
        """
        Insert a position record for a flight
        
        Args:
            flight_id: ID of the flight
            position_data: dict with lat, lon, altitude, speed, etc.
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO positions (
                    flight_id, ts, lat, lon, altitude, speed,
                    track, heading, vertical_rate, squawk, distance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                flight_id,
                position_data.get('timestamp', datetime.now().isoformat()),
                position_data.get('lat'),
                position_data.get('lon'),
                position_data.get('altitude'),
                position_data.get('speed'),
                position_data.get('track'),
                position_data.get('heading'),
                position_data.get('vertical_rate'),
                position_data.get('squawk'),
                position_data.get('distance')
            ))
            
            conn.commit()
            conn.close()
    
    def log_flight_event(self, flight_id, event_type, event_data=None, aircraft_icao=None):
        """
        Log a flight event (uses existing flight_events table)
        
        Args:
            flight_id: ID of the flight (can be None for aircraft-level events)
            event_type: Type of event (new_flight, callsign_change, gap_detected, etc.)
            event_data: Optional dict with additional event data
            aircraft_icao: Optional ICAO if flight_id is None
        """
        # Merge flight_id into event_data for storage
        if event_data is None:
            event_data = {}
        if flight_id is not None:
            event_data['flight_id'] = flight_id
        
        # Use existing save_event method
        self.save_event(
            icao=aircraft_icao or 'system',
            event_type=event_type,
            event_data=event_data
        )
    
    def get_flights(self, start_time=None, end_time=None, callsign=None, icao=None, active_only=False, limit=None):
        """
        Get flights matching criteria
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            callsign: Optional callsign filter
            icao: Optional aircraft ICAO filter
            active_only: If True, only return active flights (end_time IS NULL)
            limit: Optional limit on number of results
            
        Returns:
            List of flight dictionaries
        """
        # Don't use lock for read operations - SQLite handles concurrency
        # This prevents blocking when server is writing positions
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=3.0)
            # Enable WAL mode for concurrent reads/writes
            conn.execute('PRAGMA journal_mode=WAL')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = '''
                SELECT f.*, a.registration, a.type, a.model, a.manufacturer
                FROM flights f
                LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
                WHERE 1=1
            '''
            params = []
            
            if active_only:
                query += ' AND f.end_time IS NULL'
            if start_time:
                query += ' AND f.start_time >= ?'
                params.append(start_time)
            if end_time:
                query += ' AND f.end_time <= ?'
                params.append(end_time)
            if callsign:
                query += ' AND f.callsign = ?'
                params.append(callsign)
            if icao:
                query += ' AND f.aircraft_icao = ?'
                params.append(icao)
            
            query += ' ORDER BY f.start_time DESC'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
            return result
        except sqlite3.OperationalError as e:
            print(f"      ✗ Database error in get_flights(): {e}")
            raise
        except Exception as e:
            print(f"      ✗ Error in get_flights(): {e}")
            raise
        finally:
            # Always close connection, even on error
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_flight(self, flight_id):
        """
        Get a specific flight by ID
        
        Args:
            flight_id: ID of the flight
            
        Returns:
            Flight dictionary or None
        """
        # Don't use lock for read operations
        try:
            conn = sqlite3.connect(self.db_path, timeout=3.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT f.*, a.registration, a.type, a.model, a.manufacturer
                FROM flights f
                LEFT JOIN aircraft a ON f.aircraft_icao = a.icao
                WHERE f.id = ?
            ''', (flight_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            print(f"      ✗ Error in get_flight(): {e}")
            return None
    
    def get_flight_positions(self, flight_id, start_time=None, end_time=None, limit=None):
        """
        Get position data for a flight
        
        Args:
            flight_id: ID of the flight
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Optional limit on number of results
            
        Returns:
            List of position dictionaries
        """
        # Don't use lock for read operations - SQLite handles concurrency with WAL mode
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=3.0)
            # Enable WAL mode for concurrent reads/writes
            conn.execute('PRAGMA journal_mode=WAL')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = '''
                SELECT ts, lat, lon, altitude, speed, track, heading,
                       vertical_rate, squawk, distance
                FROM positions
                WHERE flight_id = ?
            '''
            params = [flight_id]
            
            if start_time:
                query += ' AND ts >= ?'
                params.append(start_time)
            if end_time:
                query += ' AND ts <= ?'
                params.append(end_time)
            
            query += ' ORDER BY ts'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"      ✗ Error in get_flight_positions(): {e}")
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_flight_position_count(self, flight_id):
        """
        Get count of positions for a flight (efficient - doesn't load all data)
        
        Args:
            flight_id: ID of the flight
            
        Returns:
            Integer count of positions
        """
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM positions WHERE flight_id = ?', (flight_id,))
            count = cursor.fetchone()[0]
            conn.close()
            
            return count
    
    def get_flight_position_counts(self, flight_ids):
        """
        Get position counts for multiple flights efficiently (single query)
        
        Args:
            flight_ids: List of flight IDs
            
        Returns:
            Dictionary mapping flight_id -> position_count
        """
        if not flight_ids:
            return {}
        
        conn = None
        try:
            # Use a shorter timeout and don't wait for lock too long
            conn = sqlite3.connect(self.db_path, timeout=2.0)  # Short timeout
            cursor = conn.cursor()
            
            # Create placeholders for IN clause
            placeholders = ','.join('?' * len(flight_ids))
            cursor.execute(f'''
                SELECT flight_id, COUNT(*) as count
                FROM positions
                WHERE flight_id IN ({placeholders})
                GROUP BY flight_id
            ''', flight_ids)
            
            results = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Fill in zeros for flights with no positions
            result = {fid: results.get(fid, 0) for fid in flight_ids}
            return result
        except sqlite3.OperationalError as e:
            print(f"⚠️  Database lock/timeout error in get_flight_position_counts: {e}")
            # Return empty dict on error - position counts are not critical
            return {}
        except Exception as e:
            print(f"⚠️  Error in get_flight_position_counts: {e}")
            return {}
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def get_aircraft_flights(self, icao, limit=None):
        """
        Get all flights for an aircraft
        
        Args:
            icao: Aircraft ICAO code
            limit: Optional limit on number of results
            
        Returns:
            List of flight dictionaries
        """
        return self.get_flights(icao=icao, limit=limit)
    
    def get_aircraft(self, icao):
        """
        Get aircraft information
        
        Args:
            icao: Aircraft ICAO code
            
        Returns:
            Aircraft dictionary or None
        """
        # Don't use lock for read operations - SQLite handles concurrency
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=3.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM aircraft WHERE icao = ?', (icao,))
            
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
        except sqlite3.OperationalError as e:
            print(f"      ✗ Database error in get_aircraft(): {e}")
            raise
        except Exception as e:
            print(f"      ✗ Error in get_aircraft(): {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def list_aircraft(self, limit=None):
        """
        List all aircraft
        
        Args:
            limit: Optional limit on number of results
            
        Returns:
            List of aircraft dictionaries
        """
        # Don't use lock for read operations - SQLite handles concurrency
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=3.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = 'SELECT * FROM aircraft ORDER BY last_seen_at DESC'
            if limit:
                query += ' LIMIT ?'
                cursor.execute(query, (limit,))
            else:
                cursor.execute(query)
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError as e:
            print(f"      ✗ Database error in list_aircraft(): {e}")
            raise
        except Exception as e:
            print(f"      ✗ Error in list_aircraft(): {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass


