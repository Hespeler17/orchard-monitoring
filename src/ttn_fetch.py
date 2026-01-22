#!/usr/bin/env python3
"""
Fetch data from The Things Network (TTN) API
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

TTN_APP_ID = os.getenv('TTN_APP_ID')
TTN_API_KEY = os.getenv('TTN_API_KEY')
TTN_REGION = os.getenv('TTN_REGION', 'eu1')

# TTN API endpoint
BASE_URL = f"https://{TTN_REGION}.cloud.thethings.network/api/v3"

def test_api_connection():
    """
    Test basic API connection
    """
    url = f"{BASE_URL}/applications/{TTN_APP_ID}"
    
    headers = {
        "Authorization": f"Bearer {TTN_API_KEY}"
    }
    
    try:
        print("Testing API connection...")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            print("✅ API connection successful!")
            app_data = response.json()
            print(f"Application: {app_data.get('name', 'N/A')}")
            return True
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def get_devices():
    """
    Get list of devices in application
    """
    url = f"{BASE_URL}/applications/{TTN_APP_ID}/devices"
    
    headers = {
        "Authorization": f"Bearer {TTN_API_KEY}"
    }
    
    try:
        print("\nFetching devices...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        devices = response.json().get('end_devices', [])
        print(f"✅ Found {len(devices)} device(s)")
        
        for device in devices:
            device_id = device['ids']['device_id']
            print(f"   📡 {device_id}")
        
        return devices
    
    except Exception as e:
        print(f"❌ Error fetching devices: {e}")
        return []

def get_uplink_messages(limit=10):
    """
    Fetch recent uplink messages from TTN Storage API
    """
    url = f"{BASE_URL}/as/applications/{TTN_APP_ID}/packages/storage/uplink_message"
    
    headers = {
        "Authorization": f"Bearer {TTN_API_KEY}",
        "Accept": "text/event-stream"
    }
    
    params = {
        "limit": limit,
        "order": "-received_at"
    }
    
    try:
        print(f"\nFetching uplink messages (limit={limit})...")
        response = requests.get(url, headers=headers, params=params, stream=True, timeout=10)
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 404:
            print("⚠️  Storage Integration might not be enabled")
            print("   Enable it in TTN Console:")
            print("   Applications → Integrations → Storage Integration")
            return None
        
        response.raise_for_status()
        
        messages = []
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data:'):
                    try:
                        data = json.loads(line_str[5:])
                        messages.append(data)
                    except json.JSONDecodeError:
                        continue
        
        return messages
    
    except requests.exceptions.Timeout:
        print("❌ Request timeout - no data available")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")
        return None

def parse_sensor_data(message):
    """
    Parse KIWI sensor data from TTN message
    """
    try:
        device_id = message['result']['end_device_ids']['device_id']
        received_at = message['result']['received_at']
        
        # Parse decoded payload
        decoded = message['result']['uplink_message'].get('decoded_payload', {})
        
        # Get RSSI and SNR
        metadata = message['result']['uplink_message']['rx_metadata'][0]
        rssi = metadata.get('rssi')
        snr = metadata.get('snr')
        
        print(f"\n📡 Device: {device_id}")
        print(f"🕐 Time: {received_at}")
        print(f"📶 RSSI: {rssi} dBm | SNR: {snr} dB")
        print("-" * 60)
        
        # Print all sensor values
        if decoded:
            for key, value in decoded.items():
                print(f"   {key}: {value}")
        else:
            print("   ⚠️  No decoded payload")
        
        return {
            'device_id': device_id,
            'timestamp': received_at,
            'rssi': rssi,
            'snr': snr,
            'data': decoded
        }
    
    except (KeyError, IndexError) as e:
        print(f"⚠️  Error parsing message: {e}")
        return None

def main():
    """
    Main function
    """
    print("=" * 60)
    print("TTN DATA FETCHER - Orchard Monitoring System")
    print("=" * 60)
    
    # Check environment variables
    if not TTN_APP_ID or not TTN_API_KEY:
        print("❌ Error: TTN_APP_ID or TTN_API_KEY not set in .env file")
        return
    
    print(f"\nApplication ID: {TTN_APP_ID}")
    print(f"Region: {TTN_REGION}")
    print("-" * 60)
    
    # Test API connection
    if not test_api_connection():
        return
    
    # Get devices
    devices = get_devices()
    
    if not devices:
        print("\n⚠️  No devices found. Add devices in TTN Console.")
        return
    
    # Fetch messages
    messages = get_uplink_messages(limit=10)
    
    if messages:
        print(f"\n✅ Fetched {len(messages)} messages")
        print("=" * 60)
        
        # Parse each message
        for msg in messages:
            parse_sensor_data(msg)
    else:
        print("\n❌ No messages in storage")
        print("\nPossible reasons:")
        print("1. Storage Integration not enabled in TTN Console")
        print("2. No recent uplinks from devices")
        print("3. Data retention period expired")
        print("\nCheck TTN Console → Live data for recent activity")

if __name__ == "__main__":
    main()
