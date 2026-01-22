#!/usr/bin/env python3
"""
Database management for sensor data
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'sensors.db'

def init_database():
    """Initialize database with required tables"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uplink_id INTEGER NOT NULL,
            sensor_name TEXT NOT NULL,
            sensor_value REAL NOT NULL,
            unit TEXT,
            FOREIGN KEY (uplink_id) REFERENCES uplinks(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized: {DB_PATH}")

def save_uplink(device_id, timestamp, gateway_id, rssi, snr, sensor_data):
    """Save uplink and sensor data to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO uplinks (device_id, timestamp, gateway_id, rssi, snr)
        VALUES (?, ?, ?, ?, ?)
    ''', (device_id, timestamp, gateway_id, rssi, snr))
    
    uplink_id = cursor.lastrowid
    
    for key, value in sensor_data.items():
        unit = None
        if 'frequency' in key.lower():
            unit = 'kHz'
        elif 'temperature' in key.lower():
            unit = '°C'
        elif 'lux' in key.lower():
            unit = 'lux'
        elif 'humidity' in key.lower():
            unit = '%'
        
        cursor.execute('''
            INSERT INTO sensor_data (uplink_id, sensor_name, sensor_value, unit)
            VALUES (?, ?, ?, ?)
        ''', (uplink_id, key, value, unit))
    
    conn.commit()
    conn.close()
    return uplink_id

def get_database_stats():
    """Get database statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM uplinks')
    uplink_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM sensor_data')
    reading_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT device_id) FROM uplinks')
    device_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'uplinks': uplink_count,
        'readings': reading_count,
        'devices': device_count
    }

if __name__ == "__main__":
    init_database()
    stats = get_database_stats()
    print(f"\nDatabase Statistics:")
    print(f"  Uplinks: {stats['uplinks']}")
    print(f"  Sensor readings: {stats['readings']}")
    print(f"  Devices: {stats['devices']}")
