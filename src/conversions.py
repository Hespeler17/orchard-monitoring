#!/usr/bin/env python3
"""
Watermark 200SS soil moisture sensor: frequency (kHz) to kPa conversion.

Uses the Mills lookup table for non-linear conversion from Watermark
sensor resistance to soil water tension (kPa), with temperature
compensation per the Shock/Barnum/Seyfried equation.

References:
  - Watermark 200SS-5 sensor datasheet (Irrometer)
  - Mills calibration table for Watermark sensors
  - Shock, Barnum, Seyfried (1998) temperature compensation
"""


# ---------------------------------------------------------------------------
# Mills lookup table: resistance (kohm) -> kPa
# Non-linear relationship - must interpolate between points
# ---------------------------------------------------------------------------

MILLS_TABLE = [
    # (resistance_kohm, kpa)
    (0.0,    0),
    (0.55,   0),
    (1.0,    9),
    (1.5,   15),
    (2.0,   20),
    (2.5,   24),
    (3.0,   28),
    (3.5,   32),
    (4.0,   36),
    (4.5,   40),
    (5.0,   44),
    (5.5,   48),
    (6.0,   52),
    (7.0,   60),
    (8.0,   68),
    (9.0,   76),
    (10.0,  84),
    (12.0, 100),
    (15.0, 124),
    (20.0, 160),
    (25.0, 195),
    (30.0, 218),
    (35.0, 240),
    (40.0, 255),
]


def _interpolate_mills(resistance_kohm):
    """Interpolate kPa from resistance using the Mills table.

    Args:
        resistance_kohm: Sensor resistance in kilohms.

    Returns:
        Soil water tension in kPa (0 = saturated, higher = drier).
    """
    if resistance_kohm <= MILLS_TABLE[0][0]:
        return MILLS_TABLE[0][1]

    if resistance_kohm >= MILLS_TABLE[-1][0]:
        return MILLS_TABLE[-1][1]

    for i in range(len(MILLS_TABLE) - 1):
        r_low, kpa_low = MILLS_TABLE[i]
        r_high, kpa_high = MILLS_TABLE[i + 1]

        if r_low <= resistance_kohm <= r_high:
            # Linear interpolation between table points
            fraction = (resistance_kohm - r_low) / (r_high - r_low)
            return kpa_low + fraction * (kpa_high - kpa_low)

    return MILLS_TABLE[-1][1]


# ---------------------------------------------------------------------------
# KIWI sensor: frequency (kHz) to resistance (kohm)
# ---------------------------------------------------------------------------

# The KIWI sensor excites the Watermark with an AC signal and measures
# the response frequency. Higher frequency = higher resistance = drier soil.
#
# The KIWI board outputs frequency in kHz. The conversion to resistance
# uses the relationship:
#   resistance_kohm = frequency_khz / FREQUENCY_DIVISOR
#
# This is calibrated so that typical field values map to sensible
# Watermark resistance ranges (0.55 - 40 kohm).
#
# Typical KIWI frequency readings:
#   ~200 kHz  = very wet  (~0.5 kohm)
#   ~1400 kHz = moderate  (~3.5 kohm)
#   ~4000 kHz = dry       (~10 kohm)
#   ~8000 kHz = very dry  (~20 kohm)

FREQUENCY_DIVISOR = 400.0  # Calibration: kohm = freq_khz / divisor


def frequency_to_resistance(frequency_khz):
    """Convert KIWI sensor frequency to Watermark resistance.

    Args:
        frequency_khz: Sensor excitation frequency in kHz.

    Returns:
        Resistance in kilohms, or None if frequency is invalid.
    """
    if frequency_khz is None or frequency_khz <= 0:
        return None
    return frequency_khz / FREQUENCY_DIVISOR


# ---------------------------------------------------------------------------
# Temperature compensation (Shock/Barnum/Seyfried 1998)
# ---------------------------------------------------------------------------

def compensate_temperature(kpa_at_ref, temperature_c, ref_temp=24.0):
    """Apply temperature compensation to kPa reading.

    The Watermark sensor's resistance changes with temperature.
    This applies the Shock/Barnum/Seyfried correction to normalize
    readings to the reference temperature.

    Args:
        kpa_at_ref: kPa value from Mills table (at reference conditions).
        temperature_c: Actual soil/sensor temperature in Celsius.
        ref_temp: Reference temperature for the Mills table (default 24°C).

    Returns:
        Temperature-compensated kPa value.
    """
    if temperature_c is None or kpa_at_ref is None:
        return kpa_at_ref

    if kpa_at_ref <= 0:
        return 0.0

    # Shock/Barnum/Seyfried temperature correction factor
    # At ref_temp the factor is 1.0, warmer soil reads lower, cooler reads higher
    correction = 1.0 + 0.018 * (temperature_c - ref_temp)

    if correction <= 0:
        correction = 0.01  # Safety floor

    compensated = kpa_at_ref / correction
    return max(0.0, compensated)


# ---------------------------------------------------------------------------
# Main conversion: frequency -> kPa
# ---------------------------------------------------------------------------

def frequency_to_kpa(frequency_khz, temperature_c=None):
    """Convert Watermark frequency reading to soil water tension in kPa.

    Full pipeline: frequency -> resistance -> Mills table -> temp compensation.

    Args:
        frequency_khz: KIWI sensor frequency in kHz.
        temperature_c: Optional soil temperature for compensation.

    Returns:
        dict with:
            - kpa: Soil water tension (0=saturated, higher=drier)
            - resistance_kohm: Intermediate resistance value
            - temperature_compensated: Whether temp compensation was applied
            - raw_kpa: kPa before temperature compensation
    """
    resistance = frequency_to_resistance(frequency_khz)
    if resistance is None:
        return None

    raw_kpa = _interpolate_mills(resistance)

    if temperature_c is not None:
        kpa = compensate_temperature(raw_kpa, temperature_c)
        temp_compensated = True
    else:
        kpa = raw_kpa
        temp_compensated = False

    return {
        'kpa': round(kpa, 1),
        'resistance_kohm': round(resistance, 2),
        'temperature_compensated': temp_compensated,
        'raw_kpa': round(raw_kpa, 1),
    }


# ---------------------------------------------------------------------------
# Irrigation status classification
# ---------------------------------------------------------------------------

# Thresholds for fruit trees / apple orchard (sandy loam to clay loam)
IRRIGATION_THRESHOLDS = {
    'saturated':    (0, 10),     # 0-10 kPa: saturated, no irrigation needed
    'optimal':      (10, 33),    # 10-33 kPa: ideal range for fruit trees
    'moderate':     (33, 60),    # 33-60 kPa: getting dry, monitor closely
    'dry':          (60, 100),   # 60-100 kPa: irrigation recommended
    'very_dry':     (100, 200),  # 100-200 kPa: stress, irrigate immediately
    'critical':     (200, None), # >200 kPa: severe stress / sensor limit
}


def get_irrigation_status(kpa):
    """Classify soil moisture status for irrigation decisions.

    Args:
        kpa: Soil water tension in kPa.

    Returns:
        dict with:
            - status: Status code (saturated/optimal/moderate/dry/very_dry/critical)
            - label: Human-readable Swedish label
            - color: Color code for display (green/yellow/orange/red)
            - action: Recommended action in Swedish
    """
    if kpa is None:
        return {
            'status': 'unknown',
            'label': 'Okänd',
            'color': 'white',
            'action': 'Sensorfel eller saknad data',
        }

    classifications = [
        ('saturated', 0,   10,  'Mättad',       'green',  'Ingen bevattning behövs. Marken är mättad.'),
        ('optimal',   10,  33,  'Optimal',      'green',  'Perfekt fuktnivå för fruktträd.'),
        ('moderate',  33,  60,  'Måttlig',      'yellow', 'Bevaka noga. Bevattning kan behövas snart.'),
        ('dry',       60,  100, 'Torr',         'orange', 'Bevattning rekommenderas.'),
        ('very_dry',  100, 200, 'Mycket torr',  'red',    'Bevattna omedelbart! Stressrisk.'),
        ('critical',  200, 999, 'Kritisk',      'red',    'Akut torka! Bevattna nu.'),
    ]

    for status, low, high, label, color, action in classifications:
        if low <= kpa < high:
            return {
                'status': status,
                'label': label,
                'color': color,
                'action': action,
                'kpa': round(kpa, 1),
            }

    # Fallback for extremely high values
    return {
        'status': 'critical',
        'label': 'Kritisk',
        'color': 'red',
        'action': 'Akut torka! Bevattna nu.',
        'kpa': round(kpa, 1),
    }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Mills kPa Conversion Test")
    print("=" * 60)

    # Test with typical KIWI frequency values
    test_cases = [
        (100,  22, "Very wet soil (low frequency)"),
        (500,  22, "Wet soil"),
        (1000, 22, "Optimal range"),
        (1500, 22, "Moderate - monitor"),
        (3000, 22, "Dry soil"),
        (6000, 22, "Very dry soil"),
        (1500,  5, "Moderate, cold (5°C)"),
        (1500, 35, "Moderate, hot (35°C)"),
    ]

    for freq, temp, desc in test_cases:
        result = frequency_to_kpa(freq, temp)
        status = get_irrigation_status(result['kpa'])
        print(f"\n{desc}:")
        print(f"  Frequency:   {freq} kHz")
        print(f"  Resistance:  {result['resistance_kohm']} kohm")
        print(f"  Raw kPa:     {result['raw_kpa']}")
        print(f"  Comp. kPa:   {result['kpa']} (temp={temp}°C)")
        print(f"  Status:      {status['label']} ({status['status']})")
        print(f"  Action:      {status['action']}")
