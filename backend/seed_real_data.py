"""
seed_real_data.py — Load real EIA + NASA CSV data into the new DB tables.

Run from the backend/ directory:
    python seed_real_data.py

This reads the pre-generated CSV files in data/ and populates:
  - eia_readings   (from miso_carbon_6month.csv)
  - nasa_readings  (from renewable_6month_extended.csv)
"""

import asyncio
import os

import pandas as pd

from database import engine, async_session, Base, EIAReading, NASAReading

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
EIA_CSV = os.path.join(DATA_DIR, "miso_carbon_6month.csv")
NASA_CSV = os.path.join(DATA_DIR, "renewable_6month_extended.csv")


async def seed_eia():
    """Load MISO carbon + generation data from EIA CSV."""
    if not os.path.exists(EIA_CSV):
        print(f"[EIA] CSV not found: {EIA_CSV} — skipping.")
        return

    df = pd.read_csv(EIA_CSV)
    df["period"] = pd.to_datetime(df["period"])
    print(f"[EIA] Loaded {len(df)} rows from CSV.")

    # Column mapping from EIA fuel codes to our schema
    #   BAT=battery, COL=coal, NG=natural gas, NUC=nuclear,
    #   OTH=other, SUN=solar, WAT=hydro, WND=wind
    fuel_map = {
        "COL": "coal_mw", "NG": "gas_mw", "NUC": "nuclear_mw",
        "SUN": "solar_mw", "WND": "wind_mw", "WAT": "hydro_mw",
        "BAT": "battery_mw", "OTH": "other_mw",
    }

    # Clear existing EIA data
    async with async_session() as db:
        await db.execute(EIAReading.__table__.delete())
        await db.commit()
    print("[EIA] Cleared existing eia_readings.")

    readings = []
    for _, row in df.iterrows():
        ts = row["period"].to_pydatetime()

        # Extract MW values (default 0 for missing fuel types)
        mw = {v: float(row.get(k, 0) or 0) for k, v in fuel_map.items()}
        total = sum(mw.values())

        # Compute percentages
        pcts = {}
        if total > 0:
            pcts["solar_pct"] = round(mw["solar_mw"] / total * 100, 2)
            pcts["wind_pct"] = round(mw["wind_mw"] / total * 100, 2)
            pcts["gas_pct"] = round(mw["gas_mw"] / total * 100, 2)
            pcts["coal_pct"] = round(mw["coal_mw"] / total * 100, 2)
            pcts["nuclear_pct"] = round(mw["nuclear_mw"] / total * 100, 2)
            pcts["hydro_pct"] = round(mw["hydro_mw"] / total * 100, 2)
            pcts["other_pct"] = round((mw["other_mw"] + mw["battery_mw"]) / total * 100, 2)
        else:
            pcts = {k: 0.0 for k in ["solar_pct", "wind_pct", "gas_pct", "coal_pct",
                                       "nuclear_pct", "hydro_pct", "other_pct"]}

        ci = float(row.get("carbon_intensity", 0) or 0)

        readings.append(EIAReading(
            timestamp=ts,
            date=ts.date(),
            zone="US-MISO",
            carbon_intensity=round(ci, 2),
            total_mw=round(total, 2),
            **mw,
            **pcts,
        ))

    # Bulk insert
    async with async_session() as db:
        batch = 200
        for i in range(0, len(readings), batch):
            db.add_all(readings[i:i + batch])
            await db.commit()
            print(f"  [EIA] Inserted {min(i + batch, len(readings))}/{len(readings)}")

    print(f"[EIA] Done — {len(readings)} rows inserted.")


async def seed_nasa():
    """Load NASA POWER renewable/weather data from CSV."""
    if not os.path.exists(NASA_CSV):
        print(f"[NASA] CSV not found: {NASA_CSV} — skipping.")
        return

    df = pd.read_csv(NASA_CSV)
    df["datetime"] = pd.to_datetime(df["datetime"])
    print(f"[NASA] Loaded {len(df)} rows from CSV.")

    # Clear existing NASA data
    async with async_session() as db:
        await db.execute(NASAReading.__table__.delete())
        await db.commit()
    print("[NASA] Cleared existing nasa_readings.")

    readings = []
    for _, row in df.iterrows():
        ts = row["datetime"].to_pydatetime()
        readings.append(NASAReading(
            timestamp=ts,
            date=ts.date(),
            solar_irradiance=float(row.get("solar", 0) or 0),
            clear_sky_solar=float(row.get("clear_sky_solar", 0) or 0),
            wind_speed=float(row.get("wind50", 0) or 0),
            cloud_cover=float(row.get("cloud", 0) or 0),
            temperature=float(row.get("temp", 0) or 0),
            renewable_index=float(row.get("renewable_index", 0) or 0),
        ))

    # Bulk insert
    async with async_session() as db:
        batch = 500
        for i in range(0, len(readings), batch):
            db.add_all(readings[i:i + batch])
            await db.commit()
            print(f"  [NASA] Inserted {min(i + batch, len(readings))}/{len(readings)}")

    print(f"[NASA] Done — {len(readings)} rows inserted.")


async def main():
    # Create tables (including new ones)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables ensured.\n")

    await seed_eia()
    print()
    await seed_nasa()

    print("\n=== Real data seeding complete. ===")
    print("Switch to real data by setting:  GREENQUEUE_DATA_SOURCE=real python server.py")


if __name__ == "__main__":
    asyncio.run(main())
