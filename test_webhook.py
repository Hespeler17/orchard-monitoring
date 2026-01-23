import requests
import json

# Mock TTN data
mock_data = {
    "end_device_ids": {
        "device_id": "kiwi-001"
    },
    "received_at": "2026-01-22T12:00:00.000Z",
    "uplink_message": {
        "decoded_payload": {
            "input5_frequency_khz": 1402,
            "input6_frequency_khz": 1398,
            "light_intensity_lux": 150,
            "mcu_temperature_c": 22
        },
        "rx_metadata": [{
            "gateway_ids": {"gateway_id": "test-gateway"},
            "rssi": -75,
            "snr": 12.5
        }]
    }
}

# Send to webhook
print("Sending test data to webhook...")
response = requests.post(
    'http://localhost:5001/webhook',
    json=mock_data,
    headers={'Content-Type': 'application/json'}
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Check stats
stats_response = requests.get('http://localhost:5001/stats')
print(f"\nDatabase stats: {stats_response.json()}")
