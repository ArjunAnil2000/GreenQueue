"""
server.py — Single FastAPI app with all routes + background job executor.

Run from the backend/ directory:
    python server.py
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from database import init_db, get_db, Job, async_session
from model import train_model, predict_next_24h
from scheduler import suggest_green_windows
from config import DATA_SOURCE, get_zone
from data_source import (
    get_current_energy as ds_get_current_energy,
    get_history as ds_get_history,
    get_stats as ds_get_stats,
    get_heatmap_data as ds_get_heatmap_data,
    ingest_current_reading as ds_ingest_current_reading,
)
from region_carbon import fetch_region_carbon


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class JobCreate(BaseModel):
    name: str
    task_type: str = "general"
    duration_hours: int = 1

class JobSchedule(BaseModel):
    job_id: int
    window_index: int = 0


# ---------------------------------------------------------------------------
# Background job executor — checks every 30s for jobs whose start time arrived
# ---------------------------------------------------------------------------
async def hourly_ingestion_loop():
    """Insert a new reading every time a new hour rolls over.

    Mock  → generates via sine functions and stores in carbon_readings.
    Real  → no live ingestion yet (data comes from CSV seed).
    Both  → retrain the ML model on the active data source.
    """
    last_inserted_hour: int | None = None
    while True:
        try:
            now = datetime.now(timezone.utc)
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            hour_key = int(current_hour.timestamp())

            if hour_key != last_inserted_hour:
                result = await ds_ingest_current_reading()
                if result:
                    print(f"[ingest] Inserted reading for {result['timestamp']} — {result['carbon_intensity']} gCO2/kWh")
                else:
                    print(f"[ingest] No live ingestion for source={DATA_SOURCE} (seeded from CSV)")

                last_inserted_hour = hour_key

                # Re-train model so the 24h forecast window shifts
                try:
                    stats = train_model()
                    print(f"[ingest] Model retrained — MAE {stats['mae']}, rows {stats['rows_used']}")
                except Exception as te:
                    print(f"[ingest] Model retrain skipped: {te}")
        except Exception as e:
            print(f"Ingestion error: {e}")

        await asyncio.sleep(30)


async def job_executor_loop():
    """Simulate job execution: scheduled->running->completed based on time."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)

                # Move scheduled -> running if start time has passed
                result = await db.execute(
                    select(Job).where(Job.status == "scheduled", Job.scheduled_start <= now)
                )
                for job in result.scalars().all():
                    job.status = "running"
                await db.commit()

                # Move running -> completed if end time has passed
                result = await db.execute(
                    select(Job).where(Job.status == "running", Job.scheduled_end <= now)
                )
                for job in result.scalars().all():
                    job.status = "completed"
                    job.completed_at = now
                await db.commit()
        except Exception as e:
            print(f"Executor error: {e}")

        await asyncio.sleep(30)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print(f"[startup] DATA_SOURCE = {DATA_SOURCE}")
    executor_task = asyncio.create_task(job_executor_loop())
    ingest_task = asyncio.create_task(hourly_ingestion_loop())
    yield
    executor_task.cancel()
    ingest_task.cancel()

app = FastAPI(title="GreenQueue", lifespan=lifespan)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "GreenQueue API running"}


# ---------------------------------------------------------------------------
# Energy + Forecast
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    """Return the active data source so the frontend can display it."""
    return {"data_source": DATA_SOURCE, "zone": get_zone()}


@app.get("/api/energy/current")
async def get_current_energy(db: AsyncSession = Depends(get_db)):
    return await ds_get_current_energy(db)


@app.get("/api/energy/history")
async def get_energy_history(limit: int = 168, db: AsyncSession = Depends(get_db)):
    return await ds_get_history(db, limit)


@app.get("/api/energy/stats")
async def get_energy_stats(db: AsyncSession = Depends(get_db)):
    return await ds_get_stats(db)


@app.get("/api/energy/heatmap")
async def get_heatmap(db: AsyncSession = Depends(get_db)):
    """Return avg carbon intensity by hour (0-23) x day-of-week (0-6) for heatmap."""
    return await ds_get_heatmap_data(db)


@app.get("/api/regions/carbon")
async def get_region_carbon():
    """Compare live carbon intensity across GCP cloud regions."""
    return await fetch_region_carbon()


@app.post("/api/forecast/train")
async def train_forecast():
    stats = train_model()
    return stats


@app.get("/api/forecast/next24h")
async def forecast_next24h(db: AsyncSession = Depends(get_db)):
    predictions = predict_next_24h()
    # Attach recent actuals so the frontend can overlay real vs predicted
    recent = await ds_get_history(db, limit=5)
    # Sort ascending by timestamp (get_history returns desc)
    recent.sort(key=lambda r: r["timestamp"])
    return {"forecast": predictions, "actuals": recent}


# ---------------------------------------------------------------------------
# Job + Scheduler
# ---------------------------------------------------------------------------
@app.post("/api/jobs/suggest")
async def suggest_job_windows(body: JobCreate, db: AsyncSession = Depends(get_db)):
    job = Job(name=body.name, task_type=body.task_type, duration_hours=body.duration_hours)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    windows = suggest_green_windows(body.duration_hours)

    return {
        "job_id": job.id,
        "job_name": job.name,
        "duration_hours": job.duration_hours,
        "suggestions": windows,
    }


@app.post("/api/jobs/schedule")
async def schedule_job(body: JobSchedule, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == body.job_id))
    job = result.scalar_one_or_none()
    if not job:
        return {"error": "Job not found"}

    windows = suggest_green_windows(job.duration_hours)
    if body.window_index >= len(windows):
        return {"error": "Invalid window index"}

    chosen = windows[body.window_index]

    job.status = "scheduled"
    job.scheduled_start = datetime.fromisoformat(chosen["start"])
    job.scheduled_end = datetime.fromisoformat(chosen["end"])
    job.avg_carbon = chosen["avg_carbon"]
    job.naive_carbon = chosen["naive_carbon"]
    job.carbon_saved = chosen["savings_vs_naive"]
    await db.commit()
    await db.refresh(job)

    return {
        "job_id": job.id, "name": job.name, "status": job.status,
        "scheduled_start": job.scheduled_start.isoformat() + "+00:00",
        "scheduled_end": job.scheduled_end.isoformat() + "+00:00",
        "avg_carbon": job.avg_carbon,
        "naive_carbon": job.naive_carbon,
        "carbon_saved": job.carbon_saved,
    }


@app.get("/api/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).order_by(Job.created_at.desc()))
    jobs = result.scalars().all()
    return [
        {
            "id": j.id, "name": j.name, "task_type": j.task_type,
            "duration_hours": j.duration_hours, "status": j.status,
            "scheduled_start": (j.scheduled_start.isoformat() + "+00:00") if j.scheduled_start else None,
            "scheduled_end": (j.scheduled_end.isoformat() + "+00:00") if j.scheduled_end else None,
            "avg_carbon": j.avg_carbon, "naive_carbon": j.naive_carbon,
            "carbon_saved": j.carbon_saved,
            "completed_at": (j.completed_at.isoformat() + "+00:00") if j.completed_at else None,
            "created_at": j.created_at.isoformat() + "+00:00",
        }
        for j in jobs
    ]


@app.get("/api/jobs/stats")
async def job_stats(db: AsyncSession = Depends(get_db)):
    # Count by status
    result_all = await db.execute(
        select(func.count(Job.id), func.sum(Job.carbon_saved))
        .where(Job.status.in_(["scheduled", "running", "completed"]))
    )
    row_all = result_all.one()

    result_running = await db.execute(
        select(func.count(Job.id)).where(Job.status == "running")
    )
    running = result_running.scalar() or 0

    result_completed = await db.execute(
        select(func.count(Job.id)).where(Job.status == "completed")
    )
    completed = result_completed.scalar() or 0

    return {
        "total_scheduled": row_all[0] or 0,
        "total_carbon_saved": round(row_all[1] or 0, 1),
        "running_count": running,
        "completed_count": completed,
    }


@app.get("/api/jobs/impact")
async def job_impact(db: AsyncSession = Depends(get_db)):
    """Return data for impact comparison chart: scheduled vs naive carbon per job."""
    result = await db.execute(
        select(Job)
        .where(Job.status.in_(["scheduled", "running", "completed"]))
        .order_by(Job.created_at.asc())
    )
    jobs = result.scalars().all()

    comparison = []
    cumulative_saved = 0
    for j in jobs:
        cumulative_saved += max(0, j.carbon_saved * j.duration_hours)
        comparison.append({
            "name": j.name,
            "smart_carbon": j.avg_carbon,
            "naive_carbon": j.naive_carbon,
            "saved_per_hour": j.carbon_saved,
            "total_saved": round(j.carbon_saved * j.duration_hours, 1),
            "cumulative_saved": round(cumulative_saved, 1),
        })

    return comparison


# ---------------------------------------------------------------------------
# Delete a pending job
# ---------------------------------------------------------------------------
@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a job only if it is still pending (not yet scheduled/running/completed)."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "scheduled"):
        raise HTTPException(status_code=400, detail=f"Cannot delete job with status '{job.status}'. Only pending or scheduled jobs can be removed.")
    await db.delete(job)
    await db.commit()
    return {"deleted": True, "id": job_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
