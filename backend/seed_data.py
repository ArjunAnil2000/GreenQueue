"""
seed_data.py — Generate 6 months of hourly carbon readings.

Run from the backend/ directory:
    python seed_data.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from database import engine, async_session, Base, CarbonReading
from mock_energy import generate_mock_carbon_data, generate_mock_power_breakdown


async def seed():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables ready.")

    # Clear old data
    async with async_session() as db:
        await db.execute(CarbonReading.__table__.delete())
        await db.commit()
    print("Cleared existing data.")

    # Generate 6 months of hourly readings
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=180)
    zone = "US-CAL-CISO"
    readings = []
    current = start

    while current <= now:
        carbon = generate_mock_carbon_data(zone=zone, timestamp=current)
        breakdown = generate_mock_power_breakdown(zone=zone, timestamp=current)
        readings.append(CarbonReading(
            timestamp=current, date=current.date(), zone=zone,
            carbon_intensity=carbon["carbonIntensity"],
            solar_pct=breakdown["solar_pct"], wind_pct=breakdown["wind_pct"],
            gas_pct=breakdown["gas_pct"], coal_pct=breakdown["coal_pct"],
            nuclear_pct=breakdown["nuclear_pct"], hydro_pct=breakdown["hydro_pct"],
            other_pct=breakdown["other_pct"],
        ))
        current += timedelta(hours=1)

    print(f"Generated {len(readings)} readings ({start.date()} → {now.date()}).")

    # Bulk insert
    async with async_session() as db:
        batch = 500
        for i in range(0, len(readings), batch):
            db.add_all(readings[i:i + batch])
            await db.commit()
            print(f"  Inserted {min(i + batch, len(readings))}/{len(readings)}")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
