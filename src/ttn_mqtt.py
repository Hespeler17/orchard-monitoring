#!/usr/bin/env python3
"""
Real-time data from TTN using MQTT
"""

import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Load environment variables
load_dotenv()

TTN_APP_ID = os.getenv('TTN_APP_ID')
TTN_API_KEY = os.getenv('TTN_API_KEY')
TTN_REGION = os.getenv('TTN_REGION', 'eu1')

# MQTT settings
MQTT_SERVER = f"{TTN_REGION}.cloud.thethings.network"
MQTT_PORT = 1883
MQTT_USERNAME = f"{TTN_APP_ID}@ttn"
MQTT_PASSWORD = TTN_API_KEY
MQTT_TOPIC = f"v3/{TTN_APP_ID}@ttn/devices/+/up"

def on_connect(client, userdata, flags, rc):
    """Called when connected to MQTT broker"""
    if rc == 0:
        print("✅ Connected to TTN MQTT broker")
        print(f"📡 Listening for uplinks from: {TTN_APP_ID}")
        print("-" * 60)
        print("Waiting for messages... (Press Ctrl+C to stop)")
        print("=" * 60)
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ Connection failed with code {rc}")
        if rc == 5:
            print("   Check your API key!")

def on_message(client, userdata, msg):
    """Called when a message is received"""
    try:
        payload = json.loads(msg.payload.decode())
        
        # Extract device info
        device_id = payload['end_device_ids']['device_id']
        received_at = payload['received_at']
        
        # Extract sensor data
        decoded = payload.get('uplink_message', {}).get('decoded_payload', {})
        
        # Extract metadata
        rx_metadata = payload.get('uplink_message', {}).get('rx_metadata', [])
        if rx_metadata:
            rssi = rx_metadata[0].get('rssi', 'N/A')
            snr = rx_metadata[0].get('snr', 'N/A')
            gateway_id = rx_metadata[0].get('gateway_ids', {}).get('gateway_id', 'N/A')
        else:
            rssi = snr = gateway_id = 'N/A'
        
        # Print formatted data
        print(f"\n📡 NEW UPLINK RECEIVED")
        print(f"{'=' * 60}")
        print(f"Device:   {device_id}")
        print(f"Time:     {received_at}")
        print(f"Gateway:  {gateway_id}")
        print(f"RSSI:     {rssi} dBm")
        print(f"SNR:      {snr} dB")
        print(f"{'-' * 60}")
        
        if decoded:
            print("Sensor Data:")
            for key, value in decoded.items():
                # Format sensor names
                key_formatted = key.replace('_', ' ').title()
                print(f"  {key_formatted:.<40} {value}")
        else:
            print("⚠️  No decoded payload")
        
        print(f"{'=' * 60}\n")
        
    except Exception as e:
        print(f"⚠️  Error parsing message: {e}")

def on_disconnect(client, userdata, rc):
    """Called when disconnected from MQTT broker"""
    if rc != 0:
        print(f"\n⚠️  Unexpected disconnection. Code: {rc}")
        print("Attempting to reconnect...")

def main():
    """Main function"""
    print("=" * 60)
    print("TTN MQTT LISTENER - Orchard Monitoring System")
    print("=" * 60)
    
    # Check environment variables
    if not TTN_APP_ID or not TTN_API_KEY:
        print("❌ Error: TTN_APP_ID or TTN_API_KEY not set in .env file")
        return
    
    print(f"\nApplication: {TTN_APP_ID}")
    print(f"Region:      {TTN_REGION}")
    print(f"MQTT Server: {MQTT_SERVER}")
    print("-" * 60)
    print("Connecting to TTN MQTT broker...")
    
    # Create MQTT client
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # Set callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    try:
        # Connect to MQTT broker
        client.connect(MQTT_SERVER, MQTT_PORT, 60)
        
        # Start loop (blocking)
        client.loop_forever()
        
    except KeyboardInterrupt:
        print("\n\n👋 Disconnecting...")
        client.disconnect()
        print("✅ Disconnected gracefully")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        client.disconnect()

if __name__ == "__main__":
    main()
