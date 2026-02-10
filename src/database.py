#!/usr/bin/env python3
"""
Database management for orchard monitoring sensor data.

Schema:
  - devices: One row per sensor device
  - sensor_types: All possible sensor types with thresholds
  - readings: One row per sensor reading
  - mills_periods: Apple scab (äppleskorv) infection periods
  - irrigation_events: Irrigation log
  - spray_applications: Spray application log
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'sensors.db'


def get_connection():
    """Get a database connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database with all required tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    cursor = conn.cursor()

    # -- 1. DEVICES
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL UNIQUE,
            device_type TEXT,
            location TEXT,
            latitude REAL,
            longitude REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # -- 2. SENSOR_TYPES
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            unit TEXT,
            category TEXT,
            min_value REAL,
            max_value REAL,
            optimal_min REAL,
            optimal_max REAL,
            warning_min REAL,
            warning_max REAL,
            critical_min REAL,
            critical_max REAL
        )
    ''')

    # -- 3. READINGS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uplink_id INTEGER,
            device_id TEXT NOT NULL,
            reading_time TEXT NOT NULL,
            sensor_type_id INTEGER NOT NULL,
            sensor_index INTEGER DEFAULT 0,
            raw_value REAL,
            raw_unit TEXT,
            calculated_value REAL,
            calculated_unit TEXT,
            quality TEXT,
            status TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(device_id),
            FOREIGN KEY (sensor_type_id) REFERENCES sensor_types(id)
        )
    ''')

    # -- 4. MILLS_PERIODS (apple scab infection periods)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mills_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            avg_temperature REAL,
            wetness_hours REAL,
            infection_level TEXT,
            infection_pressure TEXT,
            spray_recommended INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
        )
    ''')

    # -- 5. IRRIGATION_EVENTS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS irrigation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            event_time TEXT NOT NULL,
            event_type TEXT,
            water_amount_liters REAL,
            notes TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(device_id)
        )
    ''')

    # -- 6. SPRAY_APPLICATIONS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spray_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            application_date TEXT NOT NULL,
            product_name TEXT,
            active_ingredient TEXT,
            related_period_id INTEGER,
            FOREIGN KEY (device_id) REFERENCES devices(device_id),
            FOREIGN KEY (related_period_id) REFERENCES mills_periods(id)
        )
    ''')

    # -- Keep legacy uplinks table for radio metadata
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uplinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            gateway_id TEXT,
            rssi INTEGER,
            snr REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # -- Indexes for common queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_readings_device_time
        ON readings(device_id, reading_time)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_readings_sensor_type
        ON readings(sensor_type_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_mills_periods_device
        ON mills_periods(device_id)
    ''')

    conn.commit()

    # Seed default sensor types if empty
    cursor.execute('SELECT COUNT(*) FROM sensor_types')
    if cursor.fetchone()[0] == 0:
        _seed_sensor_types(conn)

    conn.close()
    print(f"Database initialized: {DB_PATH}")


def _seed_sensor_types(conn):
    """Insert default sensor type definitions for KIWI sensors."""
    sensor_types = [
        # type_code, display_name, unit, category,
        # min, max, optimal_min, optimal_max,
        # warning_min, warning_max, critical_min, critical_max
        (
            'soil_moisture_frequency', 'Markfukt (frekvens)', 'kHz', 'soil',
            200, 3000, 1000, 2000,
            800, 2200, 500, 2500
        ),
        (
            'soil_moisture_kpa', 'Markfukt (tryck)', 'kPa', 'soil',
            0, 200, 10, 33,
            33, 100, 100, 200
        ),
        (
            'temperature', 'Temperatur', '°C', 'climate',
            -40, 85, 5, 30,
            0, 35, -10, 40
        ),
        (
            'light_intensity', 'Ljusintensitet', 'lux', 'climate',
            0, 120000, 10000, 80000,
            None, None, None, None
        ),
        (
            'humidity', 'Luftfuktighet', '%', 'climate',
            0, 100, 40, 80,
            30, 90, 20, 95
        ),
        (
            'leaf_wetness', 'Bladfukt', 'min', 'disease',
            0, 1440, None, None,
            None, None, None, None
        ),
        (
            'battery_voltage', 'Batterispänning', 'V', 'device',
            0, 5, 3.3, 4.2,
            3.0, None, 2.8, None
        ),
    ]

    conn.executemany('''
        INSERT INTO sensor_types
            (type_code, display_name, unit, category,
             min_value, max_value, optimal_min, optimal_max,
             warning_min, warning_max, critical_min, critical_max)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sensor_types)
    conn.commit()
    print(f"  Seeded {len(sensor_types)} sensor types")


# ---------------------------------------------------------------------------
# Sensor name -> sensor_type mapping
# ---------------------------------------------------------------------------

_SENSOR_NAME_MAP = {
    'input5_frequency_khz': ('soil_moisture_frequency', 1),
    'input6_frequency_khz': ('soil_moisture_frequency', 2),
    'mcu_temperature_c': ('temperature', 0),
    'light_intensity_lux': ('light_intensity', 0),
}


def _resolve_sensor_type(conn, sensor_name):
    """Map a TTN payload key to (sensor_type_id, sensor_index, raw_unit).

    Returns (sensor_type_id, sensor_index, raw_unit) or None if unknown.
    """
    entry = _SENSOR_NAME_MAP.get(sensor_name)
    if entry:
        type_code, index = entry
        row = conn.execute(
            'SELECT id, unit FROM sensor_types WHERE type_code = ?',
            (type_code,)
        ).fetchone()
        if row:
            return row['id'], index, row['unit']
    return None


# ---------------------------------------------------------------------------
# Device registration
# ---------------------------------------------------------------------------

def ensure_device(conn, device_id, device_type=None):
    """Make sure a device row exists, insert if missing. Returns device_id."""
    row = conn.execute(
        'SELECT device_id FROM devices WHERE device_id = ?',
        (device_id,)
    ).fetchone()
    if not row:
        conn.execute(
            'INSERT INTO devices (device_id, device_type) VALUES (?, ?)',
            (device_id, device_type)
        )
        conn.commit()
    return device_id


# ---------------------------------------------------------------------------
# Save uplink (main entry point for incoming data)
# ---------------------------------------------------------------------------

def save_uplink(device_id, timestamp, gateway_id, rssi, snr, sensor_data):
    """Save an uplink with all sensor readings to the database.

    This is the primary function called by both webhook_server and ttn_mqtt_save.
    It writes to the legacy uplinks table (radio metadata) and the new readings
    table (one row per sensor value).

    Returns the uplink_id.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Ensure device exists
    ensure_device(conn, device_id)

    # Save radio metadata in uplinks table
    cursor.execute('''
        INSERT INTO uplinks (device_id, timestamp, gateway_id, rssi, snr)
        VALUES (?, ?, ?, ?, ?)
    ''', (device_id, timestamp, gateway_id, rssi, snr))
    uplink_id = cursor.lastrowid

    # Save each sensor value as a reading
    for key, value in sensor_data.items():
        resolved = _resolve_sensor_type(conn, key)
        if resolved:
            sensor_type_id, sensor_index, raw_unit = resolved
            cursor.execute('''
                INSERT INTO readings
                    (uplink_id, device_id, reading_time, sensor_type_id,
                     sensor_index, raw_value, raw_unit, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (uplink_id, device_id, timestamp, sensor_type_id,
                  sensor_index, value, raw_unit, 'raw'))
        else:
            # Unknown sensor: store with a dynamic sensor type
            sensor_type_id = _get_or_create_sensor_type(conn, key, value)
            cursor.execute('''
                INSERT INTO readings
                    (uplink_id, device_id, reading_time, sensor_type_id,
                     sensor_index, raw_value, raw_unit, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (uplink_id, device_id, timestamp, sensor_type_id,
                  0, value, None, 'raw'))

    conn.commit()
    conn.close()
    return uplink_id


def _get_or_create_sensor_type(conn, sensor_name, value):
    """Get or create a sensor_type for an unknown TTN payload key."""
    # Derive a type_code from the sensor name
    type_code = sensor_name.lower().strip()

    row = conn.execute(
        'SELECT id FROM sensor_types WHERE type_code = ?',
        (type_code,)
    ).fetchone()
    if row:
        return row['id']

    # Guess unit from name
    unit = None
    if 'frequency' in type_code:
        unit = 'kHz'
    elif 'temperature' in type_code or '_c' in type_code:
        unit = '°C'
    elif 'lux' in type_code:
        unit = 'lux'
    elif 'humidity' in type_code:
        unit = '%'

    display_name = sensor_name.replace('_', ' ').title()

    conn.execute('''
        INSERT INTO sensor_types (type_code, display_name, unit, category)
        VALUES (?, ?, ?, ?)
    ''', (type_code, display_name, unit, 'auto'))
    conn.commit()

    return conn.execute(
        'SELECT id FROM sensor_types WHERE type_code = ?',
        (type_code,)
    ).fetchone()['id']


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_database_stats():
    """Get database statistics."""
    conn = get_connection()

    stats = {}
    stats['uplinks'] = conn.execute('SELECT COUNT(*) FROM uplinks').fetchone()[0]
    stats['readings'] = conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
    stats['devices'] = conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]
    stats['sensor_types'] = conn.execute('SELECT COUNT(*) FROM sensor_types').fetchone()[0]

    conn.close()
    return stats


def get_latest_readings(device_id=None, limit=20):
    """Get the most recent readings, optionally filtered by device."""
    conn = get_connection()
    if device_id:
        rows = conn.execute('''
            SELECT r.*, st.display_name, st.unit, st.type_code
            FROM readings r
            JOIN sensor_types st ON r.sensor_type_id = st.id
            WHERE r.device_id = ?
            ORDER BY r.reading_time DESC
            LIMIT ?
        ''', (device_id, limit)).fetchall()
    else:
        rows = conn.execute('''
            SELECT r.*, st.display_name, st.unit, st.type_code
            FROM readings r
            JOIN sensor_types st ON r.sensor_type_id = st.id
            ORDER BY r.reading_time DESC
            LIMIT ?
        ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_devices():
    """Get all registered devices."""
    conn = get_connection()
    rows = conn.execute('SELECT * FROM devices ORDER BY created_at').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sensor_types():
    """Get all sensor type definitions."""
    conn = get_connection()
    rows = conn.execute('SELECT * FROM sensor_types ORDER BY category, type_code').fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Mills period helpers
# ---------------------------------------------------------------------------

def create_mills_period(device_id, start_time):
    """Start a new Mills infection period."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO mills_periods (device_id, start_time)
        VALUES (?, ?)
    ''', (device_id, start_time))
    period_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return period_id


def update_mills_period(period_id, **kwargs):
    """Update a Mills period with calculated values."""
    allowed = {
        'end_time', 'avg_temperature', 'wetness_hours',
        'infection_level', 'infection_pressure',
        'spray_recommended', 'completed'
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    set_clause = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values()) + [period_id]

    conn = get_connection()
    conn.execute(f'UPDATE mills_periods SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()


def get_mills_periods(device_id=None, active_only=False):
    """Get Mills periods, optionally filtered."""
    conn = get_connection()
    query = 'SELECT * FROM mills_periods WHERE 1=1'
    params = []
    if device_id:
        query += ' AND device_id = ?'
        params.append(device_id)
    if active_only:
        query += ' AND completed = 0'
    query += ' ORDER BY start_time DESC'

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Irrigation helpers
# ---------------------------------------------------------------------------

def log_irrigation(device_id, event_time, event_type, water_amount=None, notes=None):
    """Log an irrigation event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO irrigation_events
            (device_id, event_time, event_type, water_amount_liters, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (device_id, event_time, event_type, water_amount, notes))
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def get_irrigation_events(device_id=None, limit=50):
    """Get irrigation events."""
    conn = get_connection()
    if device_id:
        rows = conn.execute('''
            SELECT * FROM irrigation_events
            WHERE device_id = ? ORDER BY event_time DESC LIMIT ?
        ''', (device_id, limit)).fetchall()
    else:
        rows = conn.execute('''
            SELECT * FROM irrigation_events
            ORDER BY event_time DESC LIMIT ?
        ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Spray application helpers
# ---------------------------------------------------------------------------

def log_spray(device_id, application_date, product_name=None,
              active_ingredient=None, related_period_id=None):
    """Log a spray application."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO spray_applications
            (device_id, application_date, product_name,
             active_ingredient, related_period_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (device_id, application_date, product_name,
          active_ingredient, related_period_id))
    spray_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return spray_id


def get_spray_applications(device_id=None, limit=50):
    """Get spray applications."""
    conn = get_connection()
    if device_id:
        rows = conn.execute('''
            SELECT sa.*, mp.infection_level, mp.infection_pressure
            FROM spray_applications sa
            LEFT JOIN mills_periods mp ON sa.related_period_id = mp.id
            WHERE sa.device_id = ? ORDER BY sa.application_date DESC LIMIT ?
        ''', (device_id, limit)).fetchall()
    else:
        rows = conn.execute('''
            SELECT sa.*, mp.infection_level, mp.infection_pressure
            FROM spray_applications sa
            LEFT JOIN mills_periods mp ON sa.related_period_id = mp.id
            ORDER BY sa.application_date DESC LIMIT ?
        ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Migration from old schema
# ---------------------------------------------------------------------------

def migrate_legacy_data():
    """Migrate data from the old sensor_data table to the new readings table.

    Safe to run multiple times - skips uplinks that already have readings.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if old sensor_data table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='sensor_data'
    """)
    if not cursor.fetchone():
        print("  No legacy sensor_data table found, nothing to migrate.")
        conn.close()
        return 0

    # Find uplinks that haven't been migrated yet
    cursor.execute('''
        SELECT sd.uplink_id, sd.sensor_name, sd.sensor_value, sd.unit,
               u.device_id, u.timestamp
        FROM sensor_data sd
        JOIN uplinks u ON sd.uplink_id = u.id
        WHERE sd.uplink_id NOT IN (SELECT DISTINCT uplink_id FROM readings WHERE uplink_id IS NOT NULL)
    ''')
    rows = cursor.fetchall()

    if not rows:
        print("  No legacy data to migrate (already migrated or empty).")
        conn.close()
        return 0

    migrated = 0
    for row in rows:
        uplink_id, sensor_name, value, unit, device_id, timestamp = row

        # Ensure device exists
        ensure_device(conn, device_id)

        resolved = _resolve_sensor_type(conn, sensor_name)
        if resolved:
            sensor_type_id, sensor_index, raw_unit = resolved
        else:
            sensor_type_id = _get_or_create_sensor_type(conn, sensor_name, value)
            sensor_index = 0
            raw_unit = unit

        cursor.execute('''
            INSERT INTO readings
                (uplink_id, device_id, reading_time, sensor_type_id,
                 sensor_index, raw_value, raw_unit, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (uplink_id, device_id, timestamp, sensor_type_id,
              sensor_index, value, raw_unit, 'migrated'))
        migrated += 1

    conn.commit()
    conn.close()
    print(f"  Migrated {migrated} legacy readings to new schema.")
    return migrated


# ---------------------------------------------------------------------------
# Main (standalone usage)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_database()

    # Run migration if needed
    migrate_legacy_data()

    stats = get_database_stats()
    print(f"\nDatabase Statistics:")
    print(f"  Devices:      {stats['devices']}")
    print(f"  Sensor types: {stats['sensor_types']}")
    print(f"  Uplinks:      {stats['uplinks']}")
    print(f"  Readings:     {stats['readings']}")

    print(f"\nSensor Types:")
    for st in get_sensor_types():
        print(f"  {st['type_code']:.<35} {st['display_name']} ({st['unit'] or '?'})")
