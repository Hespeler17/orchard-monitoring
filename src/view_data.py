#!/usr/bin/env python3
"""
CLI tool for viewing orchard sensor data with color-coded output.

Usage:
    python view_data.py                    # Latest readings overview
    python view_data.py --soil             # Soil moisture with kPa & status
    python view_data.py --device kiwi-001  # Filter by device
    python view_data.py --convert 1402     # Quick frequency -> kPa conversion
    python view_data.py --convert 1402 --temp 22  # With temperature compensation
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_database, get_connection, get_database_stats,
    get_latest_readings, get_devices,
)
from conversions import frequency_to_kpa, get_irrigation_status


# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------

COLORS = {
    'green':  '\033[92m',
    'yellow': '\033[93m',
    'orange': '\033[38;5;208m',
    'red':    '\033[91m',
    'white':  '\033[97m',
    'gray':   '\033[90m',
    'bold':   '\033[1m',
    'reset':  '\033[0m',
    'cyan':   '\033[96m',
}


def color(text, color_name):
    """Wrap text in ANSI color codes."""
    return f"{COLORS.get(color_name, '')}{text}{COLORS['reset']}"


def status_color(status_code):
    """Map irrigation status to display color."""
    mapping = {
        'saturated': 'green',
        'optimal':   'green',
        'moderate':  'yellow',
        'dry':       'orange',
        'very_dry':  'red',
        'critical':  'red',
        'unknown':   'gray',
    }
    return mapping.get(status_code, 'white')


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------

def show_overview():
    """Show database overview with device count and recent activity."""
    stats = get_database_stats()
    devices = get_devices()

    print(color("\n  ORCHARD MONITORING", 'bold'))
    print(color("  " + "=" * 40, 'cyan'))
    print(f"  Enheter:        {stats['devices']}")
    print(f"  Sensortyper:    {stats['sensor_types']}")
    print(f"  Upplänkar:      {stats['uplinks']}")
    print(f"  Mätvärden:      {stats['readings']}")

    if devices:
        print(color("\n  Registrerade enheter:", 'bold'))
        for d in devices:
            loc = d.get('location') or 'Okänd plats'
            print(f"    {d['device_id']:<20} {loc}")


def show_latest_readings(device_id=None, limit=20):
    """Show latest readings in a formatted table."""
    readings = get_latest_readings(device_id=device_id, limit=limit)

    if not readings:
        print(color("\n  Inga mätvärden hittades.", 'yellow'))
        return

    print(color(f"\n  Senaste mätvärden", 'bold'))
    if device_id:
        print(color(f"  Enhet: {device_id}", 'cyan'))
    print(color("  " + "-" * 70, 'gray'))

    header = f"  {'Tid':<22} {'Enhet':<14} {'Sensor':<22} {'Värde':>10} {'Status':<12}"
    print(color(header, 'bold'))
    print(color("  " + "-" * 70, 'gray'))

    for r in readings:
        time_str = r['reading_time'][:19].replace('T', ' ')
        sensor = r.get('display_name', r.get('type_code', '?'))
        unit = r.get('unit', '')

        if r.get('calculated_value') is not None:
            value_str = f"{r['calculated_value']:.1f} {r.get('calculated_unit', unit)}"
            st = r.get('quality', r.get('status', ''))
        else:
            value_str = f"{r['raw_value']:.1f} {unit}" if r.get('raw_value') is not None else "—"
            st = r.get('status', '')

        # Color the status
        col = status_color(st)
        status_str = color(st, col) if st else ''

        print(f"  {time_str:<22} {r['device_id']:<14} {sensor:<22} {value_str:>10} {status_str}")


def show_soil_moisture(device_id=None, limit=20):
    """Show soil moisture readings with kPa conversion and irrigation advice."""
    conn = get_connection()

    # Show only kPa (calculated) rows; fall back to raw frequency if no kPa exists
    query = '''
        SELECT r.reading_time, r.device_id, r.sensor_index,
               r.raw_value, r.calculated_value, r.quality, r.status,
               st.type_code
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

    if not rows:
        print(color("\n  Inga markfuktmätningar hittades.", 'yellow'))
        return

    print(color(f"\n  Markfukt - Bevattningsstatus", 'bold'))
    if device_id:
        print(color(f"  Enhet: {device_id}", 'cyan'))
    print(color("  " + "-" * 78, 'gray'))

    header = f"  {'Tid':<20} {'Enhet':<12} {'S#':>2} {'kHz':>8} {'kPa':>8} {'Status':<14} {'Åtgärd'}"
    print(color(header, 'bold'))
    print(color("  " + "-" * 78, 'gray'))

    for r in rows:
        row = dict(r)
        time_str = row['reading_time'][:16].replace('T', ' ')

        kpa = row['calculated_value']
        freq = row['raw_value']
        status_info = get_irrigation_status(kpa)

        col = status_color(status_info['status'])
        kpa_str = f"{kpa:.0f}" if kpa is not None else "—"
        freq_str = f"{freq:.0f}" if freq else "—"
        status_str = color(f"{status_info['label']:<14}", col)
        action = status_info['action']

        print(f"  {time_str:<20} {row['device_id']:<12} {row['sensor_index']:>2} "
              f"{freq_str:>8} {kpa_str:>8} {status_str} {action}")


def show_conversion(frequency_khz, temperature_c=None):
    """Quick conversion: show kPa for a given frequency."""
    result = frequency_to_kpa(frequency_khz, temperature_c)
    if result is None:
        print(color("\n  Ogiltig frekvens.", 'red'))
        return

    status = get_irrigation_status(result['kpa'])
    col = status_color(status['status'])

    print(color("\n  Frekvens → kPa Konvertering", 'bold'))
    print(color("  " + "=" * 45, 'cyan'))
    print(f"  Frekvens:       {frequency_khz} kHz")
    print(f"  Resistans:      {result['resistance_kohm']} kohm")
    print(f"  kPa (rå):       {result['raw_kpa']}")
    if temperature_c is not None:
        print(f"  Temperatur:     {temperature_c} °C")
        print(f"  kPa (komp.):    {result['kpa']}")
    print()
    print(f"  Status:         {color(status['label'], col)}")
    print(f"  Rekommendation: {color(status['action'], col)}")
    print()

    # Show the scale
    _print_kpa_scale(result['kpa'])


def _print_kpa_scale(kpa_value):
    """Print a visual kPa scale with current position marked."""
    print(color("  kPa-skala:", 'bold'))
    print(f"  {color('0', 'green')}{'─' * 5}{color('10', 'green')}{'─' * 5}"
          f"{color('33', 'yellow')}{'─' * 5}{color('60', 'orange')}{'─' * 5}"
          f"{color('100', 'red')}{'─' * 5}{color('200+', 'red')}")
    print(f"  {color('Mättad', 'green'):>14} {color('Optimal', 'green'):>9} "
          f"{color('Måttlig', 'yellow'):>12} {color('Torr', 'orange'):>10} "
          f"{color('Mycket torr', 'red'):>14}")

    # Position marker
    max_display = 200
    bar_width = 40
    pos = int(min(kpa_value, max_display) / max_display * bar_width)
    marker_line = "  " + " " * pos + color("▲", 'bold')
    print(marker_line)
    print(f"  {' ' * pos}{color(f'{kpa_value:.0f} kPa', 'bold')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Visa sensordata från fruktodlingsövervakning',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exempel:
  python view_data.py                      Översikt
  python view_data.py --soil               Markfukt med bevattningsstatus
  python view_data.py --device kiwi-001    Filtrera på enhet
  python view_data.py --convert 1402       Snabbkonvertering kHz → kPa
  python view_data.py --convert 1402 --temp 22  Med temperaturkompensering
        """
    )

    parser.add_argument('--soil', action='store_true',
                        help='Visa markfukt med kPa och bevattningsrekommendationer')
    parser.add_argument('--device', type=str, default=None,
                        help='Filtrera på enhets-ID')
    parser.add_argument('--limit', type=int, default=20,
                        help='Max antal rader (standard: 20)')
    parser.add_argument('--convert', type=float, default=None,
                        help='Konvertera frekvens (kHz) till kPa')
    parser.add_argument('--temp', type=float, default=None,
                        help='Temperatur (°C) för kompensering vid --convert')

    args = parser.parse_args()

    # Ensure DB exists
    try:
        init_database()
    except Exception as e:
        print(color(f"\n  Databasfel: {e}", 'red'))
        sys.exit(1)

    if args.convert is not None:
        show_conversion(args.convert, args.temp)
    elif args.soil:
        show_soil_moisture(device_id=args.device, limit=args.limit)
    else:
        show_overview()
        show_latest_readings(device_id=args.device, limit=args.limit)

    print()


if __name__ == '__main__':
    main()
