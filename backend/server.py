"""
server.py — Single FastAPI app with all routes + background job executor.

Run from the backend/ directory:
    python server.py
"""

import os
import asyncio
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from database import init_db, get_db, Job, async_session
from model import train_model, predict_next_24h
from scheduler import suggest_green_windows
from geas_bridge import GEASBridge
from config import DATA_SOURCE, get_zone
from data_source import (
    get_current_energy as ds_get_current_energy,
    get_history as ds_get_history,
    get_stats as ds_get_stats,
    get_heatmap_data as ds_get_heatmap_data,
    ingest_current_reading as ds_ingest_current_reading,
    backfill_eia_history,
)
from region_carbon import fetch_region_carbon


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class JobCreate(BaseModel):
    name: str
    task_type: str = "general"
    flexibility_hours: int = 6          # how long the user can wait (search horizon)
    priority_class: str = "flexible"   # latency-critical | flexible | batch
    gpu_scale: int = 1                 # 1-1000 GPUs

class JobSchedule(BaseModel):
    job_id: int
    window_index: int = 0

class JobRunNow(BaseModel):
    job_id: int

class GEASJobCreate(BaseModel):
    name: str
    task_type: str = "general"
    command: str = ""
    earliest_start: str | None = None
    deadline: str | None = None
    duration_hours: int = 1


# ---------------------------------------------------------------------------
# GPU energy model: 300W TDP per GPU, scale to kWh
# ---------------------------------------------------------------------------
GPU_TDP_W = 300  # watts per GPU (A100-class)

def gpu_energy_kwh(gpu_count: int, hours: int) -> float:
    """Estimated energy consumption in kWh for a job."""
    return (GPU_TDP_W * gpu_count * hours) / 1000

def compute_co2(carbon_intensity: float, energy_kwh: float) -> float:
    """Total CO2 in grams = gCO2/kWh × kWh."""
    return round(carbon_intensity * energy_kwh, 1)

# Directory for uploaded demo files
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Background: Classic job executor (Green Windows mode)
# ---------------------------------------------------------------------------
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
                    select(Job).where(Job.status == "running",
                                      Job.scheduled_end != None,
                                      Job.scheduled_end <= now)
                )
                for job in result.scalars().all():
                    job.status = "completed"
                    job.completed_at = now
                await db.commit()
        except Exception as e:
            print(f"Executor error: {e}")

        await asyncio.sleep(30)


# ---------------------------------------------------------------------------
# Background: GEAS state sync (GEAS mode)
# ---------------------------------------------------------------------------
async def geas_sync_loop():
    """Periodically sync GEAS scheduler state with the DB."""
    geas = GEASBridge.get()
    while True:
        try:
            # 1. Update GI from live carbon data
            try:
                async with async_session() as db:
                    energy = await ds_get_current_energy(db)
                    if energy and "carbon_intensity" in energy:
                        ci = energy["carbon_intensity"]
                        gi = GEASBridge.carbon_to_gi(ci)
                        geas.update_gi(gi, carbon_intensity=ci)
            except Exception as e:
                print(f"[sync] GI update error: {e}")

            # 2. Promote pending GEAS jobs
            try:
                async with async_session() as db:
                    now = datetime.now(timezone.utc)
                    result = await db.execute(
                        select(Job).where(Job.status == "pending",
                                          Job.command != None,
                                          Job.command != "")
                    )
                    for job in result.scalars().all():
                        ready = True
                        if job.earliest_start and job.earliest_start > now:
                            ready = False
                        if ready:
                            geas.submit(job.id, job.name, job.command)
                            job.status = "queued"
                            await db.commit()
            except Exception as e:
                print(f"[sync] Pending check error: {e}")

            # 3. Flush GEAS status changes into DB
            changes = geas.pop_changes()
            if changes:
                async with async_session() as db:
                    for job_id, new_status, extra in changes:
                        result = await db.execute(select(Job).where(Job.id == job_id))
                        job = result.scalar_one_or_none()
                        if not job:
                            continue
                        job.status = new_status
                        if extra.get("pid"):
                            job.pid = extra["pid"]
                        if extra.get("exit_code") is not None:
                            job.exit_code = extra["exit_code"]
                        if extra.get("started_at") and not job.actual_start:
                            job.actual_start = extra["started_at"]
                        if new_status in ("completed", "failed"):
                            job.completed_at = datetime.now(timezone.utc)
                            if extra.get("avg_carbon") is not None:
                                job.avg_carbon = extra["avg_carbon"]
                                job.carbon_saved = max(0, job.naive_carbon - job.avg_carbon)
                    await db.commit()

            # 4. Sync live CPU intensity
            snap = geas.snapshot()
            if snap["running"]:
                async with async_session() as db:
                    for rt in snap["running"]:
                        result = await db.execute(select(Job).where(Job.id == rt["job_id"]))
                        job = result.scalar_one_or_none()
                        if job:
                            job.cpu_intensity = rt["intensity"]
                            job.pid = rt["pid"]
                    await db.commit()

        except Exception as e:
            print(f"[sync] error: {e}")

        await asyncio.sleep(5)
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



# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print(f"[startup] DATA_SOURCE = {DATA_SOURCE}")
    # Backfill EIA historical data (10 days) so charts have data on first run
    await backfill_eia_history(days=10)
    # Start the GEAS scheduler thread (available when user switches to GEAS mode)
    geas = GEASBridge.get()
    geas.start()
    # Async background loops — both run; classic executor handles Green-Windows
    # jobs while geas_sync handles GEAS jobs
    executor_task = asyncio.create_task(job_executor_loop())
    sync_task = asyncio.create_task(geas_sync_loop())
    ingest_task = asyncio.create_task(hourly_ingestion_loop())
    yield
    executor_task.cancel()
    sync_task.cancel()
    ingest_task.cancel()
    geas.stop()

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


# ===========================================================================
# GREEN WINDOWS MODE — suggest → pick window or run immediately
# ===========================================================================
@app.post("/api/jobs/suggest")
async def suggest_job_windows(body: JobCreate, db: AsyncSession = Depends(get_db)):
    energy = await ds_get_current_energy(db)
    naive_ci = energy.get("carbon_intensity", 0) if energy else 0

    job = Job(
        name=body.name,
        task_type=body.task_type,
        duration_hours=1,             # each job runs for 1 hour
        priority_class=body.priority_class,
        gpu_scale=max(1, min(1000, body.gpu_scale)),
        naive_carbon=naive_ci,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    e_kwh = gpu_energy_kwh(job.gpu_scale, job.duration_hours)
    windows = suggest_green_windows(horizon_hours=body.flexibility_hours)

    # For latency-critical: if best window isn't much greener, flag it
    best_savings = windows[0]["savings_vs_naive"] if windows else 0
    brown_warning = None
    if body.priority_class == "latency-critical" and best_savings < 5:
        brown_warning = {
            "current_ci": naive_ci,
            "potential_savings": round(compute_co2(best_savings, e_kwh), 1) if best_savings > 0 else 0,
            "message": "No significantly greener window available. You may select a window or run immediately.",
        }

    return {
        "job_id": job.id,
        "job_name": job.name,
        "flexibility_hours": body.flexibility_hours,
        "priority_class": body.priority_class,
        "gpu_scale": job.gpu_scale,
        "energy_kwh": round(e_kwh, 1),
        "naive_co2_g": compute_co2(naive_ci, e_kwh),
        "suggestions": windows,
        "brown_warning": brown_warning,
    }


@app.post("/api/jobs/upload-demo")
async def upload_demo(file: UploadFile = File(...)):
    """Upload a demo task file and return its stored filename."""
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    stored = f"{ts}_{safe_name}"
    path = os.path.join(UPLOAD_DIR, stored)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": stored, "original": file.filename}


@app.post("/api/jobs/schedule")
async def schedule_job(body: JobSchedule, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == body.job_id))
    job = result.scalar_one_or_none()
    if not job:
        return {"error": "Job not found"}

    windows = suggest_green_windows(horizon_hours=24)
    if body.window_index >= len(windows):
        return {"error": "Invalid window index"}

    chosen = windows[body.window_index]
    e_kwh = gpu_energy_kwh(job.gpu_scale, job.duration_hours)

    job.status = "scheduled"
    job.run_mode = "optimized"
    job.scheduled_start = datetime.fromisoformat(chosen["start"])
    job.scheduled_end = datetime.fromisoformat(chosen["end"])
    job.avg_carbon = chosen["avg_carbon"]
    job.naive_carbon = chosen["naive_carbon"]
    job.carbon_saved = chosen["savings_vs_naive"]
    job.energy_kwh = round(e_kwh, 1)
    job.co2_total_g = compute_co2(chosen["avg_carbon"], e_kwh)
    job.co2_naive_g = compute_co2(chosen["naive_carbon"], e_kwh)
    job.co2_saved_g = round(job.co2_naive_g - job.co2_total_g, 1)
    await db.commit()
    await db.refresh(job)

    return {
        "job_id": job.id, "name": job.name, "status": job.status,
        "run_mode": job.run_mode,
        "scheduled_start": job.scheduled_start.isoformat() + "+00:00",
        "scheduled_end": job.scheduled_end.isoformat() + "+00:00",
        "avg_carbon": job.avg_carbon,
        "naive_carbon": job.naive_carbon,
        "carbon_saved": job.carbon_saved,
        "gpu_scale": job.gpu_scale,
        "energy_kwh": job.energy_kwh,
        "co2_total_g": job.co2_total_g,
        "co2_naive_g": job.co2_naive_g,
        "co2_saved_g": job.co2_saved_g,
    }


@app.post("/api/jobs/run-now")
async def run_job_immediately(body: JobRunNow, db: AsyncSession = Depends(get_db)):
    """Run a job immediately at current carbon intensity — no green window."""
    result = await db.execute(select(Job).where(Job.id == body.job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    energy = await ds_get_current_energy(db)
    current_ci = energy.get("carbon_intensity", 0) if energy else 0
    e_kwh = gpu_energy_kwh(job.gpu_scale, job.duration_hours)

    now = datetime.now(timezone.utc)
    job.status = "running"
    job.run_mode = "immediate"
    job.scheduled_start = now
    job.scheduled_end = now + timedelta(hours=job.duration_hours)
    job.avg_carbon = current_ci
    job.naive_carbon = current_ci
    job.carbon_saved = 0
    job.energy_kwh = round(e_kwh, 1)
    job.co2_total_g = compute_co2(current_ci, e_kwh)
    job.co2_naive_g = compute_co2(current_ci, e_kwh)
    job.co2_saved_g = 0
    await db.commit()
    await db.refresh(job)

    return {
        "job_id": job.id, "name": job.name, "status": job.status,
        "run_mode": job.run_mode,
        "avg_carbon": job.avg_carbon,
        "gpu_scale": job.gpu_scale,
        "energy_kwh": job.energy_kwh,
        "co2_total_g": job.co2_total_g,
    }


# ===========================================================================
# GEAS MODE — submit to live process scheduler
# ===========================================================================
@app.post("/api/geas/submit")
async def geas_submit_job(body: GEASJobCreate, db: AsyncSession = Depends(get_db)):
    """Create a job and hand it to the GEAS scheduler."""
    now = datetime.now(timezone.utc)

    earliest = None
    if body.earliest_start:
        earliest = datetime.fromisoformat(body.earliest_start)
        if earliest.tzinfo is None:
            earliest = earliest.replace(tzinfo=timezone.utc)

    dl = None
    if body.deadline:
        dl = datetime.fromisoformat(body.deadline)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)

    energy = await ds_get_current_energy(db)
    naive_carbon = energy.get("carbon_intensity", 0) if energy else 0

    job = Job(
        name=body.name,
        task_type=body.task_type,
        command=body.command,
        duration_hours=body.duration_hours,
        earliest_start=earliest,
        deadline=dl,
        status="pending",
        naive_carbon=naive_carbon,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if (not earliest or earliest <= now) and body.command:
        geas = GEASBridge.get()
        geas.submit(job.id, job.name, job.command)
        job.status = "queued"
        await db.commit()

    return {
        "job_id": job.id,
        "name": job.name,
        "status": job.status,
        "command": job.command,
        "earliest_start": earliest.isoformat() if earliest else None,
    }


@app.get("/api/geas/status")
async def geas_status():
    """Live GEAS scheduler state."""
    geas = GEASBridge.get()
    return geas.snapshot()


# ===========================================================================
# SHARED — list, stats, impact, delete
# ===========================================================================
@app.get("/api/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).order_by(Job.created_at.desc()))
    jobs = result.scalars().all()
    return [
        {
            "id": j.id, "name": j.name, "task_type": j.task_type,
            "command": j.command or "",
            "priority_class": j.priority_class,
            "gpu_scale": j.gpu_scale,
            "run_mode": j.run_mode,
            "duration_hours": j.duration_hours, "status": j.status,
            "pid": j.pid,
            "cpu_intensity": round(j.cpu_intensity, 2) if j.cpu_intensity else 0,
            "exit_code": j.exit_code,
            "scheduled_start": (j.scheduled_start.isoformat() + "+00:00") if j.scheduled_start else None,
            "scheduled_end": (j.scheduled_end.isoformat() + "+00:00") if j.scheduled_end else None,
            "actual_start": (j.actual_start.isoformat() + "+00:00") if j.actual_start else None,
            "avg_carbon": j.avg_carbon, "naive_carbon": j.naive_carbon,
            "carbon_saved": j.carbon_saved,
            "energy_kwh": j.energy_kwh,
            "co2_total_g": j.co2_total_g,
            "co2_naive_g": j.co2_naive_g,
            "co2_saved_g": j.co2_saved_g,
            "completed_at": (j.completed_at.isoformat() + "+00:00") if j.completed_at else None,
            "created_at": j.created_at.isoformat() + "+00:00",
        }
        for j in jobs
    ]


@app.get("/api/jobs/stats")
async def job_stats(db: AsyncSession = Depends(get_db)):
    result_all = await db.execute(
        select(func.count(Job.id), func.sum(Job.co2_saved_g))
        .where(Job.status.in_(["scheduled", "queued", "running", "paused", "completed"]))
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

    result_queued = await db.execute(
        select(func.count(Job.id)).where(Job.status.in_(["queued", "paused"]))
    )
    queued = result_queued.scalar() or 0

    geas = GEASBridge.get()
    snap = geas.snapshot()

    return {
        "total_scheduled": row_all[0] or 0,
        "total_carbon_saved": round(row_all[1] or 0, 1),
        "running_count": running,
        "completed_count": completed,
        "queued_count": queued,
        "gi": snap["gi"],
        "capacity": snap["capacity"],
        "ti": snap["ti"],
    }


@app.get("/api/jobs/impact")
async def job_impact(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .where(Job.status.in_(["scheduled", "queued", "running", "paused", "completed"]))
        .order_by(Job.created_at.asc())
    )
    jobs = result.scalars().all()

    comparison = []
    cumulative_saved = 0
    for j in jobs:
        cumulative_saved += max(0, j.co2_saved_g)
        comparison.append({
            "name": j.name,
            "smart_carbon": j.avg_carbon,
            "naive_carbon": j.naive_carbon,
            "gpu_scale": j.gpu_scale,
            "energy_kwh": j.energy_kwh,
            "co2_total_g": j.co2_total_g,
            "co2_naive_g": j.co2_naive_g,
            "total_saved": round(j.co2_saved_g, 1),
            "cumulative_saved": round(cumulative_saved, 1),
            "run_mode": j.run_mode,
        })

    return comparison


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("running", "paused", "queued"):
        geas = GEASBridge.get()
        geas.cancel(job_id)
    if job.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot delete completed jobs")
    await db.delete(job)
    await db.commit()
    return {"deleted": True, "id": job_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
