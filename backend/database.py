"""
database.py — DB setup + table definitions (all in one file).

Uses async SQLAlchemy + SQLite. The database file lives at backend/data/greenqueue.db.
"""

from datetime import datetime, date
from sqlalchemy import String, Float, Integer, DateTime, Date
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------
DATABASE_URL = "sqlite+aiosqlite:///./data/greenqueue.db"

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Table: carbon_readings
# One row = one hourly snapshot of grid carbon intensity + energy mix.
# ---------------------------------------------------------------------------
class CarbonReading(Base):
    __tablename__ = "carbon_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    date: Mapped[date] = mapped_column(Date, nullable=True)
    zone: Mapped[str] = mapped_column(String, default="US-CAL-CISO")
    carbon_intensity: Mapped[float] = mapped_column(Float)
    solar_pct: Mapped[float] = mapped_column(Float, default=0.0)
    wind_pct: Mapped[float] = mapped_column(Float, default=0.0)
    gas_pct: Mapped[float] = mapped_column(Float, default=0.0)
    coal_pct: Mapped[float] = mapped_column(Float, default=0.0)
    nuclear_pct: Mapped[float] = mapped_column(Float, default=0.0)
    hydro_pct: Mapped[float] = mapped_column(Float, default=0.0)
    other_pct: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------------------
# Table: jobs
# A task the user wants to schedule at a green-energy window.
# ---------------------------------------------------------------------------
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)                          # e.g. "Train ResNet"
    task_type: Mapped[str] = mapped_column(String, default="general")  # compute / data / general
    duration_hours: Mapped[int] = mapped_column(Integer, default=1)    # estimated runtime in hours
    status: Mapped[str] = mapped_column(String, default="pending")     # pending / scheduled / running / completed
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    avg_carbon: Mapped[float] = mapped_column(Float, default=0.0)         # avg predicted intensity during window
    naive_carbon: Mapped[float] = mapped_column(Float, default=0.0)       # what carbon would be if run immediately
    carbon_saved: Mapped[float] = mapped_column(Float, default=0.0)       # gCO2 saved vs naive
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Table: eia_readings (REAL data from EIA API)
# One row = one hourly snapshot of MISO grid generation by fuel type.
# MW values are actual generation; percentages are derived.
# ---------------------------------------------------------------------------
class EIAReading(Base):
    __tablename__ = "eia_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=True)
    zone: Mapped[str] = mapped_column(String, default="US-MISO")
    carbon_intensity: Mapped[float] = mapped_column(Float)

    # Raw MW generation by fuel type
    coal_mw: Mapped[float] = mapped_column(Float, default=0.0)
    gas_mw: Mapped[float] = mapped_column(Float, default=0.0)
    nuclear_mw: Mapped[float] = mapped_column(Float, default=0.0)
    solar_mw: Mapped[float] = mapped_column(Float, default=0.0)
    wind_mw: Mapped[float] = mapped_column(Float, default=0.0)
    hydro_mw: Mapped[float] = mapped_column(Float, default=0.0)
    battery_mw: Mapped[float] = mapped_column(Float, default=0.0)
    other_mw: Mapped[float] = mapped_column(Float, default=0.0)
    total_mw: Mapped[float] = mapped_column(Float, default=0.0)

    # Derived percentages (precomputed for fast API responses)
    solar_pct: Mapped[float] = mapped_column(Float, default=0.0)
    wind_pct: Mapped[float] = mapped_column(Float, default=0.0)
    gas_pct: Mapped[float] = mapped_column(Float, default=0.0)
    coal_pct: Mapped[float] = mapped_column(Float, default=0.0)
    nuclear_pct: Mapped[float] = mapped_column(Float, default=0.0)
    hydro_pct: Mapped[float] = mapped_column(Float, default=0.0)
    other_pct: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------------------
# Table: nasa_readings (REAL data from NASA POWER API)
# One row = one hourly weather / renewable availability snapshot.
# ---------------------------------------------------------------------------
class NASAReading(Base):
    __tablename__ = "nasa_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, default=43.0731)
    longitude: Mapped[float] = mapped_column(Float, default=-89.4012)

    solar_irradiance: Mapped[float] = mapped_column(Float, default=0.0)   # ALLSKY_SFC_SW_DWN
    clear_sky_solar: Mapped[float] = mapped_column(Float, default=0.0)    # CLRSKY_SFC_SW_DWN
    wind_speed: Mapped[float] = mapped_column(Float, default=0.0)         # WS50M
    cloud_cover: Mapped[float] = mapped_column(Float, default=0.0)        # CLOUD_AMT (%)
    temperature: Mapped[float] = mapped_column(Float, default=0.0)        # T2M (°C)
    renewable_index: Mapped[float] = mapped_column(Float, default=0.0)    # composite 0–1


async def init_db():
    """Create all tables (including new real-data tables)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Yield a DB session (FastAPI dependency)."""
    async with async_session() as session:
        yield session
