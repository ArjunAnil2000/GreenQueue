"""
region_carbon.py — Fetch live carbon intensity for multiple GCP regions.

Queries the EIA API for all unique balancing authorities mapped to GCP
regions, computes carbon intensity for each, and returns a sorted list
suitable for a frontend bar-chart.

Falls back to realistic static estimates when the EIA API is unavailable
or the key is not configured.
"""

import httpx
from collections import defaultdict
from datetime import datetime, timezone

from config import EIA_API_KEY, EMISSION_FACTORS, EIA_RESPONDENT
from gcp_regions import GCP_REGION_MAP, UNIQUE_RESPONDENTS

EIA_BASE_URL = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"


# ── Static fallback estimates (gCO2/kWh, typical 2024-2025 averages) ──────
FALLBACK_ESTIMATES: dict[str, float] = {
    "MISO":  380,   # Coal + gas heavy (Midwest)
    "PJM":   350,   # Large mix, mid-Atlantic gas+nuclear
    "ERCO":  330,   # Texas — lots of wind + gas
    "CISO":  240,   # California — heavy solar + zero-carbon
    "BPAT":   80,   # Oregon/WA — dominated by hydro
    "DUK":   310,   # Carolinas — nuclear + gas + coal
    "NEVP":  360,   # Nevada — gas heavy
}


async def fetch_region_carbon() -> list[dict]:
    """
    Return a list of dicts, one per GCP region, with live (or fallback)
    carbon intensity data sorted ascending by carbon_intensity.

    Each dict:
        gcp_region, label, respondent, carbon_intensity, is_active, is_live
    """
    live_data = await _fetch_live_multi_region()

    results = []
    for region in GCP_REGION_MAP:
        resp = region["respondent"]
        ci = live_data.get(resp)
        is_live = ci is not None
        if ci is None:
            ci = FALLBACK_ESTIMATES.get(resp, 350)

        results.append({
            "gcp_region":       region["gcp_region"],
            "label":            region["label"],
            "respondent":       resp,
            "carbon_intensity": round(ci, 1),
            "is_active":        resp == EIA_RESPONDENT,
            "is_live":          is_live,
        })

    # Sort: greenest first
    results.sort(key=lambda r: r["carbon_intensity"])
    return results


async def _fetch_live_multi_region() -> dict[str, float]:
    """
    Fetch the most recent hour of generation data from EIA for all unique
    respondents.  Returns {respondent: carbon_intensity} or empty dict on failure.
    """
    if not EIA_API_KEY:
        print("[region_carbon] No EIA_API_KEY — using fallback estimates")
        return {}

    # Request the latest data for all respondents at once
    respondent_codes = [r["respondent"] for r in UNIQUE_RESPONDENTS]

    params: list[tuple[str, str]] = [
        ("frequency", "hourly"),
        ("data[0]", "value"),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("offset", "0"),
        ("length", str(len(respondent_codes) * 30)),  # ~10 fuel types × respondents × a few periods
        ("api_key", EIA_API_KEY),
    ]
    # Add each respondent as a separate facet parameter
    for code in respondent_codes:
        params.append(("facets[respondent][]", code))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(EIA_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"[region_carbon] EIA API request failed: {e}")
        return {}

    records = data.get("response", {}).get("data", [])
    if not records:
        print("[region_carbon] No records returned from EIA API")
        return {}

    # Group by (respondent, period) — only keep the most recent period per respondent
    latest_period: dict[str, str] = {}          # respondent → latest period string
    by_key: dict[tuple, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for rec in records:
        resp_id = rec.get("respondent", "")
        period = rec.get("period", "")
        fuel = rec.get("fueltype", "")
        value = rec.get("value")
        try:
            value = float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            value = 0.0

        # Track the most recent period per respondent
        if resp_id not in latest_period or period > latest_period[resp_id]:
            latest_period[resp_id] = period

        by_key[(resp_id, period)][fuel] += value

    # Compute carbon intensity for the latest period of each respondent
    result: dict[str, float] = {}
    for resp_id, period in latest_period.items():
        fuels = by_key[(resp_id, period)]
        total_mw = sum(fuels.values())
        if total_mw <= 0:
            continue

        emissions = sum(
            fuels.get(fuel, 0.0) * factor
            for fuel, factor in EMISSION_FACTORS.items()
        )
        result[resp_id] = round(emissions / total_mw, 2)

    timestamp_str = next(iter(latest_period.values()), "?")
    print(f"[region_carbon] Fetched live data for {len(result)} regions (latest period: {timestamp_str})")
    return result
