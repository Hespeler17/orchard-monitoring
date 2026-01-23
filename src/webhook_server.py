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
from database import init_database, save_uplink, get_database_stats

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
        stats = {'uplinks': 0, 'readings': 0, 'devices': 0}
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Orchard Monitoring Webhook</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #2c5f2d; }}
            .stats {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h1>🌾 Orchard Monitoring Webhook</h1>
        <h2>Status: <span style="color: green;">Running ✅</span></h2>
        <hr>
        <div class="stats">
            <h3>Database Statistics:</h3>
            <ul>
                <li>Total Uplinks: {stats['uplinks']}</li>
                <li>Sensor Readings: {stats['readings']}</li>
                <li>Devices: {stats['devices']}</li>
            </ul>
        </div>
        <hr>
        <p><strong>Webhook endpoint:</strong> <code>/webhook</code></p>
        <p><strong>Stats API:</strong> <code>/stats</code></p>
        <p><strong>Health check:</strong> <code>/health</code></p>
    </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Receive uplink from TTN webhook
    """
    try:
        # Get JSON data from TTN
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # Extract device info
        device_id = data['end_device_ids']['device_id']
        timestamp = data['received_at']
        
        # Extract sensor data from decoded payload
        decoded = data.get('uplink_message', {}).get('decoded_payload', {})
        
        # Extract metadata
        rx_metadata = data.get('uplink_message', {}).get('rx_metadata', [])
        if rx_metadata:
            rssi = rx_metadata[0].get('rssi')
            snr = rx_metadata[0].get('snr')
            gateway_id = rx_metadata[0].get('gateway_ids', {}).get('gateway_id')
        else:
            rssi = snr = gateway_id = None
        
        # Save to database
        uplink_id = save_uplink(device_id, timestamp, gateway_id, rssi, snr, decoded)
        
        # Log to console
        print(f"📡 Uplink saved (ID: {uplink_id})")
        print(f"   Device: {device_id}")
        print(f"   RSSI: {rssi} dBm, SNR: {snr} dB")
        
        # Return success
        return jsonify({
            'success': True,
            'uplink_id': uplink_id,
            'device_id': device_id,
            'timestamp': timestamp
        }), 200
        
    except KeyError as e:
        print(f"❌ Missing field: {e}")
        return jsonify({'error': f'Missing field: {e}'}), 400
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
def stats():
    """
    Get database statistics as JSON
    """
    try:
        stats = get_database_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """
    Health check endpoint
    """
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    print("=" * 60)
    print("🌾 ORCHARD MONITORING WEBHOOK SERVER")
    print("=" * 60)
    print(f"\nServer starting...")
    print(f"Webhook endpoint: http://localhost:5001/webhook")
    print(f"Stats: http://localhost:5001/stats")
    print(f"Health: http://localhost:5001/health")
    print("=" * 60)
    
    # Run server (PORT 5001 instead of 5000)
    app.run(host='0.0.0.0', port=5001, debug=True)
