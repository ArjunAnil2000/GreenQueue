"""
eia_live.py — Fetch the latest hourly generation data from the EIA API.

Returns data in the same shape as what seed_real_data.py inserts,
so it can be directly stored into the eia_readings table.
"""

import httpx
from datetime import datetime, timedelta, timezone

from config import EIA_API_KEY, EIA_RESPONDENT, EMISSION_FACTORS, REAL_ZONE

EIA_BASE_URL = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"

# Map EIA fuel codes to our DB column names
FUEL_TO_COLUMN = {
    "COL": "coal_mw",
    "NG":  "gas_mw",
    "NUC": "nuclear_mw",
    "SUN": "solar_mw",
    "WND": "wind_mw",
    "WAT": "hydro_mw",
    "BAT": "battery_mw",
    "OTH": "other_mw",
}


async def fetch_latest_eia_readings(hours_back: int = 6) -> list[dict]:
    """
    Fetch the most recent `hours_back` hours of MISO generation data
    from the EIA API. Returns a list of dicts ready to create EIAReading objects.

    Each dict has:
        timestamp, date, zone, carbon_intensity,
        coal_mw, gas_mw, nuclear_mw, solar_mw, wind_mw, hydro_mw, battery_mw, other_mw,
        total_mw, solar_pct, wind_pct, gas_pct, coal_pct, nuclear_pct, hydro_pct, other_pct
    """
    if not EIA_API_KEY:
        print("[eia_live] No EIA_API_KEY configured — skipping live fetch.")
        return []

    # EIA data is typically 2-3 hours behind real time.
    # Instead of requesting a fixed window, fetch the most recent N hours
    # by sorting descending and limiting the result count.
    params = {
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": EIA_RESPONDENT,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": hours_back * 10,   # ~10 fuel types per hour
        "api_key": EIA_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(EIA_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[eia_live] API request failed: {e}")
        return []

    records = data.get("response", {}).get("data", [])
    if not records:
        print(f"[eia_live] No records returned from EIA API")
        return []

    # Group records by period (each period has multiple fuel type rows)
    from collections import defaultdict
    by_period: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for rec in records:
        period = rec.get("period", "")
        fuel = rec.get("fueltype", "")
        value = rec.get("value")
        try:
            value = float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            value = 0.0
        by_period[period][fuel] += value

    # Convert each period into an EIAReading-compatible dict
    results = []
    for period_str, fuels in sorted(by_period.items()):
        try:
            ts = datetime.fromisoformat(period_str).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        # MW values
        mw = {}
        for eia_code, col_name in FUEL_TO_COLUMN.items():
            mw[col_name] = round(fuels.get(eia_code, 0.0), 2)

        total = sum(mw.values())

        # Carbon intensity
        emissions = sum(
            fuels.get(fuel, 0.0) * factor
            for fuel, factor in EMISSION_FACTORS.items()
        )
        carbon_intensity = round(emissions / total, 2) if total > 0 else 0.0

        # Percentages
        if total > 0:
            pcts = {
                "solar_pct": round(mw["solar_mw"] / total * 100, 2),
                "wind_pct": round(mw["wind_mw"] / total * 100, 2),
                "gas_pct": round(mw["gas_mw"] / total * 100, 2),
                "coal_pct": round(mw["coal_mw"] / total * 100, 2),
                "nuclear_pct": round(mw["nuclear_mw"] / total * 100, 2),
                "hydro_pct": round(mw["hydro_mw"] / total * 100, 2),
                "other_pct": round((mw["other_mw"] + mw["battery_mw"]) / total * 100, 2),
            }
        else:
            pcts = {k: 0.0 for k in [
                "solar_pct", "wind_pct", "gas_pct", "coal_pct",
                "nuclear_pct", "hydro_pct", "other_pct"
            ]}

        results.append({
            "timestamp": ts,
            "date": ts.date(),
            "zone": REAL_ZONE,
            "carbon_intensity": carbon_intensity,
            "total_mw": round(total, 2),
            **mw,
            **pcts,
        })

    ts_range = f"{results[0]['timestamp'].isoformat()} → {results[-1]['timestamp'].isoformat()}" if results else ""
    print(f"[eia_live] Fetched {len(results)} hourly readings from EIA ({ts_range})")
    return results
