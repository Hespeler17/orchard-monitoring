#!/usr/bin/env python3
"""
Web dashboard for orchard monitoring.

Runs on port 5002 (separate from webhook server on 5001).
Reads from the same SQLite database (data/sensors.db).

Usage:
    python dashboard_app.py
"""

import csv
import io
import sys
import os
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    Response, abort,
)

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_database, get_connection, get_database_stats,
    get_latest_readings, get_devices, get_sensor_types,
)
from conversions import get_irrigation_status

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Initialize database on startup
# ---------------------------------------------------------------------------

try:
    init_database()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")


# ---------------------------------------------------------------------------
# Helper: get current soil moisture status for all sensors
# ---------------------------------------------------------------------------

def _get_soil_status(device_id=None, limit=20):
    """Get soil moisture kPa readings with irrigation status.

    Returns list of dicts with keys:
        device_id, sensor_index, kpa, freq, time,
        status, label, color, action
    """
    conn = get_connection()
    query = '''
        SELECT r.reading_time, r.device_id, r.sensor_index,
               r.raw_value, r.calculated_value, r.quality
        FROM readings r
        JOIN sensor_types st ON r.sensor_type_id = st.id
        WHERE st.type_code = 'soil_moisture_kpa'
    '''
    params = []
    if device_id:
        query += ' AND r.device_id = ?'
        params.append(device_id)
    query += ' ORDER BY r.reading_time DESC LIMIT ?'
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        kpa = r['calculated_value']
        status_info = get_irrigation_status(kpa)
        results.append({
            'device_id': r['device_id'],
            'sensor_index': r['sensor_index'],
            'kpa': kpa if kpa is not None else 0,
            'freq': r['raw_value'] if r['raw_value'] is not None else 0,
            'time': r['reading_time'][:16].replace('T', ' '),
            'status': status_info['status'],
            'label': status_info['label'],
            'color': status_info['color'],
            'action': status_info['action'],
        })

    return results


def _get_current_soil_status(device_id=None):
    """Get only the LATEST reading per device+sensor_index."""
    all_readings = _get_soil_status(device_id=device_id, limit=200)
    seen = set()
    current = []
    for r in all_readings:
        key = (r['device_id'], r['sensor_index'])
        if key not in seen:
            seen.add(key)
            current.append(r)
    return current


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """Dashboard overview."""
    stats = get_database_stats()
    devices = get_devices()
    readings = get_latest_readings(limit=30)
    soil_status = _get_current_soil_status()

    return render_template('index.html',
                           stats=stats,
                           devices=devices,
                           readings=readings,
                           soil_status=soil_status)


@app.route('/soil-moisture')
def soil_moisture():
    """Soil moisture page with chart and table."""
    device_id = request.args.get('device_id')
    all_readings = _get_soil_status(device_id=device_id, limit=500)
    current = _get_current_soil_status(device_id=device_id)

    # Prepare chart data (chronological order for Chart.js)
    chart_data = []
    for r in reversed(all_readings):
        chart_data.append({
            'time': r['time'],
            'kpa': r['kpa'],
            'device_id': r['device_id'],
            'sensor_index': r['sensor_index'],
        })

    return render_template('soil_moisture.html',
                           readings=all_readings,
                           current=current,
                           chart_data=chart_data)


@app.route('/devices')
def devices_list():
    """List all devices."""
    devices = get_devices()
    return render_template('devices.html', devices=devices)


@app.route('/device/<device_id>')
def device_detail(device_id):
    """Detail page for a single device."""
    conn = get_connection()

    # Get device info
    device_row = conn.execute(
        'SELECT * FROM devices WHERE device_id = ?', (device_id,)
    ).fetchone()
    if not device_row:
        conn.close()
        abort(404)
    device = dict(device_row)

    # All readings for this device
    readings = get_latest_readings(device_id=device_id, limit=200)

    # Soil moisture status
    soil_status = _get_current_soil_status(device_id=device_id)

    # Uplinks (radio metadata)
    uplink_rows = conn.execute('''
        SELECT * FROM uplinks
        WHERE device_id = ?
        ORDER BY timestamp DESC LIMIT 50
    ''', (device_id,)).fetchall()
    uplinks = [dict(u) for u in uplink_rows]

    conn.close()

    # Build chart data: kPa readings + temperature
    chart_data = []
    for r in reversed(readings):
        if r.get('type_code') == 'soil_moisture_kpa' and r.get('calculated_value') is not None:
            chart_data.append({
                'time': r['reading_time'][:16].replace('T', ' '),
                'value': r['calculated_value'],
                'label': f"kPa S{r.get('sensor_index', 0)}",
                'unit': 'kPa',
            })
        elif r.get('type_code') == 'temperature' and r.get('raw_value') is not None:
            chart_data.append({
                'time': r['reading_time'][:16].replace('T', ' '),
                'value': r['raw_value'],
                'label': 'Temperatur',
                'unit': '°C',
            })

    return render_template('device.html',
                           device=device,
                           readings=readings,
                           soil_status=soil_status,
                           uplinks=uplinks,
                           chart_data=chart_data)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@app.route('/export/soil-moisture.csv')
def export_soil_csv():
    """Export soil moisture data as CSV."""
    device_id = request.args.get('device_id')
    readings = _get_soil_status(device_id=device_id, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Tid', 'Enhet', 'Sensor', 'kHz', 'kPa', 'Status', 'Rekommendation'])
    for r in readings:
        writer.writerow([
            r['time'], r['device_id'], r['sensor_index'],
            r['freq'], r['kpa'], r['label'], r['action'],
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=soil_moisture.csv'},
    )


@app.route('/export/device/<device_id>.csv')
def export_device_csv(device_id):
    """Export all readings for a device as CSV."""
    readings = get_latest_readings(device_id=device_id, limit=10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Tid', 'Sensor', 'Index', 'Rått värde', 'Enhet', 'Beräknat', 'Beräknad enhet', 'Status'])
    for r in readings:
        writer.writerow([
            r.get('reading_time', ''),
            r.get('display_name', ''),
            r.get('sensor_index', 0),
            r.get('raw_value', ''),
            r.get('raw_unit', r.get('unit', '')),
            r.get('calculated_value', ''),
            r.get('calculated_unit', ''),
            r.get('quality', r.get('status', '')),
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={device_id}.csv'},
    )


# ---------------------------------------------------------------------------
# JSON API (for AJAX / future use)
# ---------------------------------------------------------------------------

@app.route('/api/soil-moisture')
def api_soil_moisture():
    """JSON API for soil moisture data."""
    device_id = request.args.get('device_id')
    limit = request.args.get('limit', 100, type=int)
    data = _get_soil_status(device_id=device_id, limit=limit)
    return jsonify(data)


@app.route('/api/stats')
def api_stats():
    """JSON API for database stats."""
    return jsonify(get_database_stats())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("  ORCHARD MONITORING DASHBOARD")
    print("=" * 60)
    print(f"  Dashboard:  http://localhost:5002")
    print(f"  Markfukt:   http://localhost:5002/soil-moisture")
    print(f"  Enheter:    http://localhost:5002/devices")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5002, debug=True)
