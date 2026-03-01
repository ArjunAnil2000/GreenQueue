"""
data_source.py — Abstraction layer over mock and real energy data.

Every function returns data in the same shape regardless of DATA_SOURCE,
so server.py and the frontend never need to know which source is active.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import DATA_SOURCE, get_zone
from database import CarbonReading, EIAReading, NASAReading, async_session
from mock_energy import generate_mock_carbon_data, generate_mock_power_breakdown


# ── Helpers ─────────────────────────────────────────────

def _eia_row_to_api(row: EIAReading) -> dict:
    """Convert an EIAReading ORM object to the standard API dict."""
    return {
        "timestamp": row.timestamp.isoformat() + "+00:00",
        "carbon_intensity": round(row.carbon_intensity, 1),
        "solar_pct": round(row.solar_pct, 2),
        "wind_pct": round(row.wind_pct, 2),
        "gas_pct": round(row.gas_pct, 2),
        "coal_pct": round(row.coal_pct, 2),
        "nuclear_pct": round(row.nuclear_pct, 2),
        "hydro_pct": round(row.hydro_pct, 2),
    }


def _mock_row_to_api(row: CarbonReading) -> dict:
    """Convert a CarbonReading ORM object to the standard API dict."""
    return {
        "timestamp": row.timestamp.isoformat(),
        "carbon_intensity": row.carbon_intensity,
        "solar_pct": row.solar_pct,
        "wind_pct": row.wind_pct,
        "gas_pct": row.gas_pct,
        "coal_pct": row.coal_pct,
        "nuclear_pct": row.nuclear_pct,
        "hydro_pct": row.hydro_pct,
    }


# ── Current energy snapshot ─────────────────────────────

async def get_current_energy(db: AsyncSession) -> dict:
    """
    Return the current (most recent) carbon intensity + energy mix.

    Mock: generates from sine functions for right now.
    Real: returns the latest EIA reading in the DB.
    """
    zone = get_zone()

    if DATA_SOURCE == "real":
        result = await db.execute(
            select(EIAReading)
            .where(EIAReading.zone == zone)
            .order_by(EIAReading.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return {
                "zone": zone,
                "carbon_intensity": round(row.carbon_intensity, 1),
                "timestamp": row.timestamp.isoformat() + "+00:00",
                "solar_pct": round(row.solar_pct, 2),
                "wind_pct": round(row.wind_pct, 2),
                "gas_pct": round(row.gas_pct, 2),
                "coal_pct": round(row.coal_pct, 2),
                "nuclear_pct": round(row.nuclear_pct, 2),
                "hydro_pct": round(row.hydro_pct, 2),
                "other_pct": round(row.other_pct, 2),
            }
        # Fall through to mock if no real data
        print("[data_source] No real data found — falling back to mock")

    # Mock path
    carbon = generate_mock_carbon_data(zone)
    breakdown = generate_mock_power_breakdown(zone)
    return {
        "zone": zone,
        "carbon_intensity": carbon["carbonIntensity"],
        "timestamp": carbon["datetime"],
        **breakdown,
    }


# ── Historical readings ────────────────────────────────

async def get_history(db: AsyncSession, limit: int = 168) -> list[dict]:
    """Return the most recent `limit` hourly readings."""
    zone = get_zone()

    if DATA_SOURCE == "real":
        result = await db.execute(
            select(EIAReading)
            .where(EIAReading.zone == zone)
            .order_by(EIAReading.timestamp.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        if rows:
            return [_eia_row_to_api(r) for r in rows]
        print("[data_source] No real history — falling back to mock")

    # Mock path
    result = await db.execute(
        select(CarbonReading)
        .where(CarbonReading.zone == "US-CAL-CISO")
        .order_by(CarbonReading.timestamp.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [_mock_row_to_api(r) for r in rows]


# ── Aggregate stats ─────────────────────────────────────

async def get_stats(db: AsyncSession) -> dict:
    """Return avg/min/max carbon for 24h, 7d, all-time.

    Time windows are relative to the most recent reading in the DB,
    not the current wall clock — so historical datasets still produce
    meaningful 24h/7d stats.
    """
    zone = get_zone()

    if DATA_SOURCE == "real":
        Table = EIAReading
        zone_filter = zone
    else:
        Table = CarbonReading
        zone_filter = "US-CAL-CISO"

    # Find the most recent timestamp in the active table
    latest_result = await db.execute(
        select(func.max(Table.timestamp)).where(Table.zone == zone_filter)
    )
    latest_ts = latest_result.scalar()
    if not latest_ts:
        empty = {"avg": 0, "min": 0, "max": 0, "count": 0}
        return {"last_24h": empty, "last_7d": empty, "all_time": empty}

    anchor = latest_ts  # compute windows relative to newest data point

    async def period_stats(hours_back: int) -> dict:
        cutoff = anchor - timedelta(hours=hours_back)
        q = select(
            func.avg(Table.carbon_intensity),
            func.min(Table.carbon_intensity),
            func.max(Table.carbon_intensity),
            func.count(Table.id),
        ).where(Table.zone == zone_filter, Table.timestamp >= cutoff)
        result = await db.execute(q)
        row = result.one()
        return {
            "avg": round(row[0], 1) if row[0] else 0,
            "min": round(row[1], 1) if row[1] else 0,
            "max": round(row[2], 1) if row[2] else 0,
            "count": row[3] or 0,
        }

    return {
        "last_24h": await period_stats(24),
        "last_7d": await period_stats(168),
        "all_time": await period_stats(999999),
    }


# ── Heatmap data ────────────────────────────────────────

async def get_heatmap_data(db: AsyncSession) -> list[dict]:
    """Return avg carbon intensity by hour × day-of-week (last ~30 days)."""
    zone = get_zone()

    if DATA_SOURCE == "real":
        Table = EIAReading
        zone_filter = zone
    else:
        Table = CarbonReading
        zone_filter = "US-CAL-CISO"

    result = await db.execute(
        select(Table.timestamp, Table.carbon_intensity)
        .where(Table.zone == zone_filter)
        .order_by(Table.timestamp.desc())
        .limit(720)
    )
    rows = result.all()

    grid = [[[] for _ in range(24)] for _ in range(7)]
    for ts, ci in rows:
        grid[ts.weekday()][ts.hour].append(ci)

    heatmap = []
    for dow in range(7):
        for hour in range(24):
            vals = grid[dow][hour]
            heatmap.append({
                "day": dow,
                "hour": hour,
                "avg_carbon": round(sum(vals) / len(vals), 1) if vals else 0,
            })
    return heatmap


# ── Hourly ingestion (background loop) ─────────────────

async def ingest_current_reading():
    """
    Insert readings for the current hour.
    Mock  → generates via sine functions and stores in carbon_readings.
    Real  → polls the EIA API for recent hours, inserts any new rows
            into eia_readings (skips duplicates by timestamp).
    """
    if DATA_SOURCE == "real":
        from eia_live import fetch_latest_eia_readings

        new_readings = await fetch_latest_eia_readings(hours_back=6)
        if not new_readings:
            return None

        inserted = 0
        async with async_session() as db:
            for rd in new_readings:
                # Check if this timestamp already exists to avoid duplicates
                exists = await db.execute(
                    select(EIAReading.id).where(
                        EIAReading.timestamp == rd["timestamp"],
                        EIAReading.zone == rd["zone"],
                    )
                )
                if exists.scalar_one_or_none() is not None:
                    continue

                db.add(EIAReading(**rd))
                inserted += 1

            if inserted > 0:
                await db.commit()

        if inserted > 0:
            latest = new_readings[-1]
            print(f"[eia_live] Inserted {inserted} new readings into eia_readings")
            return {
                "timestamp": latest["timestamp"].isoformat(),
                "carbon_intensity": latest["carbon_intensity"],
            }
        else:
            print("[eia_live] All fetched readings already in DB — nothing new to insert")
            return None

    # Mock ingestion (original behaviour)
    now = datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    carbon = generate_mock_carbon_data(timestamp=now)
    mix = generate_mock_power_breakdown(timestamp=now)
    async with async_session() as db:
        db.add(CarbonReading(
            timestamp=current_hour,
            date=current_hour.date(),
            zone=carbon["zone"],
            carbon_intensity=carbon["carbonIntensity"],
            **mix,
        ))
        await db.commit()
    return {
        "timestamp": current_hour.isoformat(),
        "carbon_intensity": carbon["carbonIntensity"],
    }


async def backfill_eia_history(days: int = 10):
    """
    One-time startup backfill: fetch `days` worth of hourly readings from
    the EIA API and insert any that are missing from the DB.
    This gives the Historical Trend and Heatmap charts enough data.
    """
    if DATA_SOURCE != "real":
        return

    from eia_live import fetch_latest_eia_readings

    hours = days * 24
    print(f"[backfill] Fetching up to {hours} hours ({days} days) of EIA history…")

    readings = await fetch_latest_eia_readings(hours_back=hours)
    if not readings:
        print("[backfill] No readings returned from EIA API.")
        return

    inserted = 0
    async with async_session() as db:
        for rd in readings:
            exists = await db.execute(
                select(EIAReading.id).where(
                    EIAReading.timestamp == rd["timestamp"],
                    EIAReading.zone == rd["zone"],
                )
            )
            if exists.scalar_one_or_none() is not None:
                continue
            db.add(EIAReading(**rd))
            inserted += 1

        if inserted > 0:
            await db.commit()

    print(f"[backfill] Inserted {inserted} new readings (fetched {len(readings)} total).")
