#!/usr/bin/env python3
"""
Flask webhook server to receive data from TTN
"""

from flask import Flask, request, jsonify
from datetime import datetime
import json
import sys
import os

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import (
    init_database, save_uplink, get_database_stats,
    get_latest_readings, get_devices, get_sensor_types,
    get_mills_periods, get_irrigation_events, get_spray_applications,
)

app = Flask(__name__)

# Initialize database on startup
try:
    init_database()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")

@app.route('/')
def home():
    """Homepage with basic info"""
    try:
        stats = get_database_stats()
    except:
        stats = {'uplinks': 0, 'readings': 0, 'devices': 0, 'sensor_types': 0}

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Orchard Monitoring</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #2c5f2d; }}
            .stats {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>Orchard Monitoring</h1>
        <h2>Status: <span style="color: green;">Running</span></h2>
        <hr>
        <div class="stats">
            <h3>Database Statistics:</h3>
            <ul>
                <li>Devices: {stats['devices']}</li>
                <li>Sensor Types: {stats['sensor_types']}</li>
                <li>Total Uplinks: {stats['uplinks']}</li>
                <li>Sensor Readings: {stats['readings']}</li>
            </ul>
        </div>
        <hr>
        <h3>API Endpoints:</h3>
        <ul>
            <li><code>POST /webhook</code> - TTN uplink webhook</li>
            <li><code>GET /stats</code> - Database statistics</li>
            <li><code>GET /devices</code> - All devices</li>
            <li><code>GET /sensor-types</code> - All sensor types</li>
            <li><code>GET /readings?device_id=&amp;limit=</code> - Latest readings</li>
            <li><code>GET /mills-periods?device_id=&amp;active=</code> - Mills periods</li>
            <li><code>GET /irrigation?device_id=</code> - Irrigation events</li>
            <li><code>GET /sprays?device_id=</code> - Spray applications</li>
            <li><code>GET /health</code> - Health check</li>
        </ul>
    </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    """Receive uplink from TTN webhook"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data received'}), 400

        device_id = data['end_device_ids']['device_id']
        timestamp = data['received_at']
        decoded = data.get('uplink_message', {}).get('decoded_payload', {})

        rx_metadata = data.get('uplink_message', {}).get('rx_metadata', [])
        if rx_metadata:
            rssi = rx_metadata[0].get('rssi')
            snr = rx_metadata[0].get('snr')
            gateway_id = rx_metadata[0].get('gateway_ids', {}).get('gateway_id')
        else:
            rssi = snr = gateway_id = None

        uplink_id = save_uplink(device_id, timestamp, gateway_id, rssi, snr, decoded)

        print(f"Uplink saved (ID: {uplink_id}) device={device_id} RSSI={rssi} SNR={snr}")

        return jsonify({
            'success': True,
            'uplink_id': uplink_id,
            'device_id': device_id,
            'timestamp': timestamp
        }), 200

    except KeyError as e:
        print(f"Missing field: {e}")
        return jsonify({'error': f'Missing field: {e}'}), 400
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
def stats():
    """Get database statistics as JSON"""
    try:
        return jsonify(get_database_stats())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/devices')
def devices():
    """Get all registered devices"""
    try:
        return jsonify(get_devices())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sensor-types')
def sensor_types():
    """Get all sensor type definitions"""
    try:
        return jsonify(get_sensor_types())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/readings')
def readings():
    """Get latest readings, optional ?device_id= and ?limit="""
    try:
        device_id = request.args.get('device_id')
        limit = request.args.get('limit', 20, type=int)
        return jsonify(get_latest_readings(device_id=device_id, limit=limit))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/mills-periods')
def mills_periods():
    """Get Mills infection periods, optional ?device_id= and ?active=1"""
    try:
        device_id = request.args.get('device_id')
        active = request.args.get('active', '0') == '1'
        return jsonify(get_mills_periods(device_id=device_id, active_only=active))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/irrigation')
def irrigation():
    """Get irrigation events, optional ?device_id="""
    try:
        device_id = request.args.get('device_id')
        limit = request.args.get('limit', 50, type=int)
        return jsonify(get_irrigation_events(device_id=device_id, limit=limit))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sprays')
def sprays():
    """Get spray applications, optional ?device_id="""
    try:
        device_id = request.args.get('device_id')
        limit = request.args.get('limit', 50, type=int)
        return jsonify(get_spray_applications(device_id=device_id, limit=limit))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    print("=" * 60)
    print("ORCHARD MONITORING WEBHOOK SERVER")
    print("=" * 60)
    print(f"\nServer starting...")
    print(f"Webhook endpoint: http://localhost:5001/webhook")
    print(f"Stats: http://localhost:5001/stats")
    print(f"Health: http://localhost:5001/health")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5001, debug=True)
