"""
server.py — Single FastAPI app with all routes.

Run from the backend/ directory:
    python server.py

Serves the API at /api/* and the frontend at /.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import init_db, get_db, CarbonReading
from mock_energy import generate_mock_carbon_data, generate_mock_power_breakdown
from model import train_model, predict_next_24h


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="GreenQueue", lifespan=lifespan)

# Serve frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    """Serve the frontend dashboard."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "GreenQueue API is running. Put frontend files in ../frontend/"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/energy/current")
async def get_current_energy():
    """Fetch current (mock) carbon intensity + energy mix."""
    zone = "US-CAL-CISO"
    carbon = generate_mock_carbon_data(zone)
    breakdown = generate_mock_power_breakdown(zone)
    return {
        "zone": zone,
        "carbon_intensity": carbon["carbonIntensity"],
        "timestamp": carbon["datetime"],
        **breakdown,
    }


@app.get("/api/energy/history")
async def get_energy_history(limit: int = 168, db: AsyncSession = Depends(get_db)):
    """Return the most recent carbon readings from the DB (default: 1 week)."""
    query = (
        select(CarbonReading)
        .where(CarbonReading.zone == "US-CAL-CISO")
        .order_by(CarbonReading.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "carbon_intensity": r.carbon_intensity,
            "solar_pct": r.solar_pct,
            "wind_pct": r.wind_pct,
            "gas_pct": r.gas_pct,
            "coal_pct": r.coal_pct,
            "nuclear_pct": r.nuclear_pct,
            "hydro_pct": r.hydro_pct,
        }
        for r in rows
    ]


@app.post("/api/forecast/train")
async def train_forecast():
    """Train the ML model on historical data."""
    stats = train_model()
    return stats


@app.get("/api/forecast/next24h")
async def forecast_next24h():
    """Predict carbon intensity for the next 24 hours."""
    predictions = predict_next_24h()
    return predictions


# ---------------------------------------------------------------------------
# Run with: python server.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
