#!/usr/bin/env python3
"""
Real-time data from TTN using MQTT - SAVE TO DATABASE
"""

import os
import json
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from database import init_database, save_uplink, get_database_stats, get_sensor_types

load_dotenv()

TTN_APP_ID = os.getenv('TTN_APP_ID')
TTN_API_KEY = os.getenv('TTN_API_KEY')
TTN_REGION = os.getenv('TTN_REGION', 'eu1')

MQTT_SERVER = f"{TTN_REGION}.cloud.thethings.network"
MQTT_PORT = 1883
MQTT_USERNAME = f"{TTN_APP_ID}@ttn"
MQTT_PASSWORD = TTN_API_KEY
MQTT_TOPIC = f"v3/{TTN_APP_ID}@ttn/devices/+/up"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Connected to TTN MQTT broker")
        print(f"📡 Listening for uplinks from: {TTN_APP_ID}")
        
        stats = get_database_stats()
        print(f"\n💾 Database stats:")
        print(f"   Devices:    {stats['devices']}")
        print(f"   Uplinks:    {stats['uplinks']}")
        print(f"   Readings:   {stats['readings']}")
        print(f"   Sensor types: {stats['sensor_types']}")
        
        print("-" * 60)
        print("Waiting for messages... (Press Ctrl+C to stop)")
        print("=" * 60)
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        
        device_id = payload['end_device_ids']['device_id']
        timestamp = payload['received_at']
        decoded = payload.get('uplink_message', {}).get('decoded_payload', {})
        
        rx_metadata = payload.get('uplink_message', {}).get('rx_metadata', [])
        if rx_metadata:
            rssi = rx_metadata[0].get('rssi')
            snr = rx_metadata[0].get('snr')
            gateway_id = rx_metadata[0].get('gateway_ids', {}).get('gateway_id')
        else:
            rssi = snr = gateway_id = None
        
        # Save to database
        uplink_id = save_uplink(device_id, timestamp, gateway_id, rssi, snr, decoded)
        
        print(f"\n📡 UPLINK RECEIVED & SAVED (ID: {uplink_id})")
        print(f"{'=' * 60}")
        print(f"Device:   {device_id}")
        print(f"Time:     {timestamp}")
        print(f"Gateway:  {gateway_id}")
        print(f"RSSI:     {rssi} dBm")
        print(f"SNR:      {snr} dB")
        print(f"{'-' * 60}")
        
        if decoded:
            print("Sensor Data (SAVED):")
            for key, value in decoded.items():
                key_formatted = key.replace('_', ' ').title()
                print(f"  {key_formatted:.<40} {value}")
        
        print(f"{'=' * 60}\n")
        
    except Exception as e:
        print(f"⚠️  Error: {e}")

def main():
    print("=" * 60)
    print("TTN MQTT LISTENER - WITH DATABASE STORAGE")
    print("=" * 60)
    
    if not TTN_APP_ID or not TTN_API_KEY:
        print("❌ Error: Missing credentials")
        return
    
    init_database()
    
    print(f"\nApplication: {TTN_APP_ID}")
    print(f"Region:      {TTN_REGION}")
    print("-" * 60)
    print("Connecting...")
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_SERVER, MQTT_PORT, 60)
        client.loop_forever()
        
    except KeyboardInterrupt:
        print("\n\n👋 Disconnecting...")
        stats = get_database_stats()
        print(f"\n💾 Final stats:")
        print(f"   Devices:    {stats['devices']}")
        print(f"   Uplinks:    {stats['uplinks']}")
        print(f"   Readings:   {stats['readings']}")
        client.disconnect()
        print("✅ Done")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
