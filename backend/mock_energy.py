"""
mock_energy.py — Generates realistic fake carbon intensity data.

Time-of-day patterns:
  - Solar peaks at midday, zero at night
  - Wind stronger at night
  - Gas/coal fill the gap → high carbon at night, low midday
"""

import math
import random
from datetime import datetime, timezone


def _solar_pattern(hour: int) -> float:
    """Bell curve peaking at 1 PM, zero before 6 AM and after 8 PM."""
    if hour < 6 or hour > 20:
        return 0.0
    return max(0.0, math.exp(-0.5 * ((hour - 13) / 3.5) ** 2))


def _wind_pattern(hour: int) -> float:
    """Cosine wave: peaks ~3 AM, dips ~3 PM. Range 0.2–1.0."""
    return 0.6 + 0.4 * math.cos(math.radians((hour - 3) * 15))


def generate_mock_carbon_data(zone: str = "US-CAL-CISO", timestamp: datetime | None = None) -> dict:
    """Return one fake carbon intensity reading with realistic daily pattern."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    hour = timestamp.replace(minute=0, second=0, microsecond=0).hour
    solar_factor = _solar_pattern(hour)
    wind_factor = _wind_pattern(hour)

    renewable_strength = 0.6 * solar_factor + 0.4 * wind_factor
    base_intensity = 450 - (renewable_strength * 300)
    noise = random.uniform(-0.15, 0.15)
    carbon_intensity = max(50, min(500, int(base_intensity * (1 + noise))))

    return {"carbonIntensity": carbon_intensity, "datetime": timestamp.isoformat(), "zone": zone}


def generate_mock_power_breakdown(zone: str = "US-CAL-CISO", timestamp: datetime | None = None) -> dict:
    """Return a fake energy-mix breakdown that adds to 100%."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    hour = timestamp.hour
    solar = _solar_pattern(hour) * random.uniform(25, 40)
    wind = _wind_pattern(hour) * random.uniform(10, 25)
    nuclear = random.uniform(8, 20)
    hydro = random.uniform(3, 12)

    remaining = max(0, 100 - solar - wind - nuclear - hydro)
    gas = remaining * random.uniform(0.5, 0.8)
    coal = remaining - gas

    return {
        "solar_pct": round(solar, 2),
        "wind_pct": round(wind, 2),
        "gas_pct": round(max(0, gas), 2),
        "coal_pct": round(max(0, coal), 2),
        "nuclear_pct": round(nuclear, 2),
        "hydro_pct": round(hydro, 2),
        "other_pct": 0.0,
    }
