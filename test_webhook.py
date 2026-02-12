#!/usr/bin/env python3
"""
Test webhook with both KIWI-001 and KIWI-002 payload formats.

Usage:
  python test_webhook.py              # Run against live server on localhost:5001
  python test_webhook.py --offline    # Run offline unit tests (no server needed)
"""

import json
import sys
import os

# ---------------------------------------------------------------------------
# Example payloads
# ---------------------------------------------------------------------------

KIWI_001_PAYLOAD = {
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

KIWI_002_PAYLOAD = {
    "end_device_ids": {
        "device_id": "kiwi-002"
    },
    "received_at": "2026-02-10T14:30:00.000Z",
    "uplink_message": {
        "decoded_payload": {
            "watermark_1_freq_khz": 7663,
            "watermark_2_freq_khz": 6200,
            "watermark_1_kpa": 99,
            "watermark_2_kpa": 55,
            "watermark_1_status": "dry",
            "watermark_2_status": "moderate",
            "input3_temperature_c": 8.5,
            "input4_temperature_c": 12.3,
            "ambient_temperature_c": 18.7,
            "ambient_humidity_percent": 62.4,
            "mcu_temperature_c": 19.1,
            "light_intensity_lux": 34000,
            "battery_percent": 85,
            "battery_days_remaining": 120
        },
        "rx_metadata": [{
            "gateway_ids": {"gateway_id": "gw-orchard-01"},
            "rssi": -68,
            "snr": 9.8
        }]
    }
}


def test_offline():
    """Run offline unit tests using save_uplink directly."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

    from database import (
        init_database, save_uplink, get_latest_readings,
        get_connection, _fix_frequency, _battery_percent_to_voltage,
    )

    print("=" * 60)
    print("OFFLINE TESTS")
    print("=" * 60)

    # Test frequency fix
    print("\n--- Frequency fix ---")
    assert _fix_frequency(7663) == 7.663, f"Expected 7.663, got {_fix_frequency(7663)}"
    assert _fix_frequency(4200) == 4200, f"Expected 4200 (<=5000, no fix), got {_fix_frequency(4200)}"
    assert _fix_frequency(1402) == 1402, f"Expected 1402, got {_fix_frequency(1402)}"
    assert _fix_frequency(5000) == 5000, f"Expected 5000, got {_fix_frequency(5000)}"
    assert _fix_frequency(5001) == 5.001, f"Expected 5.001, got {_fix_frequency(5001)}"
    print("  PASS: frequency fix (>5000 divides by 1000)")

    # Test battery conversion
    print("\n--- Battery percent to voltage ---")
    assert _battery_percent_to_voltage(100) == 4.2, f"100% should be 4.2V"
    assert _battery_percent_to_voltage(0) == 2.8, f"0% should be 2.8V"
    assert _battery_percent_to_voltage(50) == 3.5, f"50% should be 3.5V"
    assert _battery_percent_to_voltage(85) == 3.99, f"85% should be 3.99V"
    print("  PASS: battery_percent -> voltage conversion")

    # Initialize database
    init_database()

    # Test KIWI-001 payload
    print("\n--- KIWI-001 save_uplink ---")
    decoded_001 = KIWI_001_PAYLOAD["uplink_message"]["decoded_payload"]
    uplink_id_1 = save_uplink(
        "kiwi-001-test", "2026-01-22T12:00:00.000Z",
        "test-gw", -75, 12.5, decoded_001
    )
    print(f"  Saved uplink ID: {uplink_id_1}")

    conn = get_connection()
    readings_001 = conn.execute(
        'SELECT * FROM readings WHERE uplink_id = ?', (uplink_id_1,)
    ).fetchall()
    conn.close()

    print(f"  Readings created: {len(readings_001)}")
    for r in readings_001:
        print(f"    sensor_type_id={r['sensor_type_id']} idx={r['sensor_index']} "
              f"raw={r['raw_value']} {r['raw_unit']} "
              f"calc={r['calculated_value']} {r['calculated_unit']} "
              f"status={r['status']}")

    # Expect: 2 freq raw + 2 kPa calculated + 1 light + 1 mcu_temp = 6 readings
    assert len(readings_001) == 6, f"KIWI-001 expected 6 readings, got {len(readings_001)}"
    print("  PASS: KIWI-001 produces 6 readings")

    # Test KIWI-002 payload
    print("\n--- KIWI-002 save_uplink ---")
    decoded_002 = KIWI_002_PAYLOAD["uplink_message"]["decoded_payload"]
    uplink_id_2 = save_uplink(
        "kiwi-002-test", "2026-02-10T14:30:00.000Z",
        "gw-orchard-01", -68, 9.8, decoded_002
    )
    print(f"  Saved uplink ID: {uplink_id_2}")

    conn = get_connection()
    readings_002 = conn.execute(
        'SELECT r.*, st.type_code FROM readings r '
        'JOIN sensor_types st ON r.sensor_type_id = st.id '
        'WHERE r.uplink_id = ?', (uplink_id_2,)
    ).fetchall()
    conn.close()

    print(f"  Readings created: {len(readings_002)}")
    for r in readings_002:
        print(f"    {r['type_code']:.<30} idx={r['sensor_index']} "
              f"raw={r['raw_value']} {r['raw_unit']} "
              f"calc={r['calculated_value']} {r['calculated_unit']} "
              f"status={r['status']}")

    # Expected readings for KIWI-002:
    # watermark_1_freq_khz -> soil_moisture_frequency raw (7.663 after fix)
    # watermark_1_freq_khz -> soil_moisture_kpa calculated
    # watermark_2_freq_khz -> soil_moisture_frequency raw (4.2 after fix)
    # watermark_2_freq_khz -> soil_moisture_kpa calculated
    # input3_temperature_c -> soil_temperature raw
    # input4_temperature_c -> air_temperature raw
    # ambient_temperature_c -> ambient_temperature raw
    # ambient_humidity_percent -> ambient_humidity raw
    # mcu_temperature_c -> temperature raw
    # light_intensity_lux -> light_intensity raw
    # battery_percent -> battery_voltage calculated
    # Ignored: watermark_1_kpa, watermark_2_kpa, watermark_1_status, watermark_2_status, battery_days_remaining
    expected = 11
    assert len(readings_002) == expected, \
        f"KIWI-002 expected {expected} readings, got {len(readings_002)}"
    print(f"  PASS: KIWI-002 produces {expected} readings")

    # Verify frequency fix was applied
    freq_readings = [r for r in readings_002
                     if r['type_code'] == 'soil_moisture_frequency']
    for r in freq_readings:
        assert r['raw_value'] <= 5000, \
            f"Frequency should be fixed: got {r['raw_value']} kHz"
    print("  PASS: frequency values corrected (>5000 divided by 1000)")

    # Verify ignored fields were not saved
    type_codes = [r['type_code'] for r in readings_002]
    assert 'watermark_1_kpa' not in type_codes, "watermark_1_kpa should be ignored"
    assert 'watermark_1_status' not in type_codes, "watermark_1_status should be ignored"
    print("  PASS: decoder kPa/status fields correctly ignored")

    # Verify battery conversion
    batt_readings = [r for r in readings_002 if r['type_code'] == 'battery_voltage']
    assert len(batt_readings) == 1, f"Expected 1 battery reading, got {len(batt_readings)}"
    assert batt_readings[0]['raw_value'] == 85, "Raw value should be 85 (percent)"
    assert batt_readings[0]['calculated_value'] == 3.99, \
        f"85% should convert to 3.99V, got {batt_readings[0]['calculated_value']}"
    print("  PASS: battery_percent -> battery_voltage conversion")

    print("\n" + "=" * 60)
    print("ALL OFFLINE TESTS PASSED")
    print("=" * 60)


def test_live():
    """Send test payloads to live webhook server."""
    import requests

    url = 'http://localhost:5001/webhook'
    headers = {'Content-Type': 'application/json'}

    print("=" * 60)
    print("LIVE SERVER TESTS")
    print("=" * 60)

    # Test KIWI-001
    print("\n--- Sending KIWI-001 payload ---")
    response = requests.post(url, json=KIWI_001_PAYLOAD, headers=headers)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {json.dumps(response.json(), indent=2)}")

    # Test KIWI-002
    print("\n--- Sending KIWI-002 payload ---")
    response = requests.post(url, json=KIWI_002_PAYLOAD, headers=headers)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {json.dumps(response.json(), indent=2)}")

    # Check stats
    print("\n--- Database stats ---")
    stats_response = requests.get('http://localhost:5001/stats')
    print(f"  {json.dumps(stats_response.json(), indent=2)}")

    # Check sensor types
    print("\n--- Sensor types ---")
    types_response = requests.get('http://localhost:5001/sensor-types')
    for st in types_response.json():
        print(f"  {st['type_code']:.<35} {st['display_name']} ({st.get('unit', '?')})")


if __name__ == '__main__':
    if '--offline' in sys.argv:
        test_offline()
    else:
        test_live()
