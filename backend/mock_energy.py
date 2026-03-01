"""
mock_energy.py — Generates realistic fake carbon intensity data.

Time-of-day patterns (smooth, deterministic for any timestamp):
  - Solar: bell curve peaking ~1 PM, zero before 6 AM / after 8 PM
  - Wind: stronger at night, weaker afternoon; multi-day weather cycles
  - Nuclear: near-constant base-load with slow weekly drift
  - Hydro: stable with gentle seasonal variation
  - Gas/Coal: fill the gap when renewables drop; gas dominates over coal
  - Carbon intensity: inversely correlated with renewable share
"""

import math
import hashlib
from datetime import datetime, timezone


# ── Smooth deterministic noise ──────────────────────────
def _smooth_noise(t: float, seed: int = 0) -> float:
    """
    Multi-octave sine-based noise in [-1, 1].
    Deterministic for a given (t, seed) — no random state.
    """
    val = (
        0.50 * math.sin(t * 0.2513 + seed * 1.0)
        + 0.25 * math.sin(t * 0.7921 + seed * 2.3)
        + 0.15 * math.sin(t * 1.5708 + seed * 3.7)
        + 0.10 * math.sin(t * 3.1416 + seed * 5.1)
    )
    return max(-1.0, min(1.0, val))


def _hour_index(ts: datetime) -> float:
    """Continuous hour count since epoch — gives a smooth time axis."""
    return ts.timestamp() / 3600.0


# ── Diurnal shape functions ─────────────────────────────
def _solar_curve(hour: float) -> float:
    """Smooth bell peaking at ~13:00 local, zero outside 6–20."""
    h = hour % 24
    if h < 5.5 or h > 20.5:
        return 0.0
    # Smooth ramp-up / ramp-down at edges
    if h < 6.5:
        edge = (h - 5.5)  # 0→1 over 1 hour
        return edge * math.exp(-0.5 * ((6.5 - 13) / 3.5) ** 2)
    if h > 19.5:
        edge = (20.5 - h)
        return edge * math.exp(-0.5 * ((19.5 - 13) / 3.5) ** 2)
    return math.exp(-0.5 * ((h - 13) / 3.5) ** 2)


def _wind_curve(hour: float) -> float:
    """Cosine diurnal: stronger overnight, weaker afternoon. Range ~0.2–1.0."""
    h = hour % 24
    return 0.6 + 0.4 * math.cos(math.radians((h - 3) * 15))


# ── Public generators ───────────────────────────────────

def generate_mock_carbon_data(zone: str = "US-CAL-CISO", timestamp: datetime | None = None) -> dict:
    """Return one fake carbon intensity reading with smooth daily pattern."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    t = _hour_index(timestamp)
    h = (timestamp.hour + timestamp.minute / 60.0)

    solar_factor = _solar_curve(h)
    wind_factor = _wind_curve(h)

    # Multi-day weather drift for renewables (period ~3.5 days)
    weather = 0.12 * _smooth_noise(t, seed=99)

    renewable_strength = 0.6 * solar_factor + 0.4 * wind_factor + weather
    renewable_strength = max(0.0, min(1.0, renewable_strength))

    base_intensity = 450 - (renewable_strength * 300)
    # Gentle noise (±5 %) — smooth, not random
    noise = 0.05 * _smooth_noise(t, seed=42)
    carbon_intensity = max(50, min(500, int(base_intensity * (1 + noise))))

    return {"carbonIntensity": carbon_intensity, "datetime": timestamp.isoformat(), "zone": zone}


def generate_mock_power_breakdown(zone: str = "US-CAL-CISO", timestamp: datetime | None = None) -> dict:
    """
    Return a fake energy-mix breakdown that sums to ~100 %.
    All values are smooth functions of time — no random jumps.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    t = _hour_index(timestamp)
    h = (timestamp.hour + timestamp.minute / 60.0)

    # ── Solar: 0 at night, peaks ~32 % at 1 PM ──
    solar_base = _solar_curve(h) * 32.0
    solar_drift = 3.0 * _smooth_noise(t, seed=10)  # ±3 % slow drift (clouds)
    solar = max(0.0, solar_base + solar_drift)

    # ── Wind: ~8–22 %, stronger at night, multi-day weather cycles ──
    wind_diurnal = _wind_curve(h)
    wind_weather = 0.35 * _smooth_noise(t, seed=20)  # big multi-day swings
    wind = max(2.0, 15.0 * (wind_diurnal * 0.6 + 0.4) + 7.0 * wind_weather)

    # ── Nuclear: stable base-load ~11–15 %, very slow weekly drift ──
    nuclear = 13.0 + 2.0 * _smooth_noise(t * 0.15, seed=30)

    # ── Hydro: ~5–9 %, gentle seasonal + daily variation ──
    hydro = 7.0 + 2.0 * _smooth_noise(t * 0.3, seed=40)

    # ── Gas + Coal: fill the remainder ──
    renewables_total = solar + wind + nuclear + hydro
    remaining = max(0.0, 100.0 - renewables_total)

    # Gas share: ~60–75 % of fossil, with slow drift
    gas_share = 0.68 + 0.07 * _smooth_noise(t * 0.2, seed=50)
    gas = remaining * gas_share
    coal = remaining * (1.0 - gas_share)

    # Normalize to exactly 100 %
    total = solar + wind + nuclear + hydro + gas + coal
    if total > 0:
        factor = 100.0 / total
        solar *= factor
        wind *= factor
        nuclear *= factor
        hydro *= factor
        gas *= factor
        coal *= factor

    return {
        "solar_pct": round(solar, 2),
        "wind_pct": round(wind, 2),
        "gas_pct": round(max(0, gas), 2),
        "coal_pct": round(max(0, coal), 2),
        "nuclear_pct": round(nuclear, 2),
        "hydro_pct": round(hydro, 2),
        "other_pct": 0.0,
    }
