"""
database.py — DB setup + table definitions (all in one file).

Uses async SQLAlchemy + SQLite. The database file lives at backend/data/greenqueue.db.
"""

from datetime import datetime, date
from sqlalchemy import String, Float, DateTime, Date
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


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Yield a DB session (FastAPI dependency)."""
    async with async_session() as session:
        yield session
