import requests
import json

mock_data = {
    "end_device_ids": {
        "device_id": "kiwi-001"
    },
    "received_at": "2026-01-23T09:00:00.000Z",
    "uplink_message": {
        "decoded_payload": {
            "input5_frequency_khz": 1405,
            "input6_frequency_khz": 1400,
            "light_intensity_lux": 200,
            "mcu_temperature_c": 24
        },
        "rx_metadata": [{
            "gateway_ids": {"gateway_id": "kona-micro-gateway-001"},
            "rssi": -69,
            "snr": 14.2
        }]
    }
}

print("Sending test data to PythonAnywhere webhook...")
response = requests.post(
    'https://hespeler17.pythonanywhere.com/webhook',
    json=mock_data,
    headers={'Content-Type': 'application/json'}
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

stats_response = requests.get('https://hespeler17.pythonanywhere.com/stats')
print(f"\nDatabase stats: {stats_response.json()}")
