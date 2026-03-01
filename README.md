# GreenQueue — Carbon-Aware AI Job Scheduler

> **CheeseHacks 2026** | Smart scheduling meets sustainability

GreenQueue is an intelligent job scheduler that automatically shifts compute workloads to times when the electrical grid is cleanest. By combining real-time carbon intensity data with a machine learning forecasting model, GreenQueue finds the optimal execution windows that minimize CO2 emissions — without any manual intervention.

---

## Team

| Name | Role |
|------|------|
| Arjun Anil | Backend / ML |
| Chenglong Yu | Data Engineering |
| Shivansh Gupta | Full-Stack / Architecture |
| Sudhi Sharma | Frontend / Visualization |

---

## The Problem

Cloud computing and data centers account for ~1% of global electricity use. Most jobs are scheduled without considering *when* the grid is greenest. During peak solar hours, carbon intensity can drop 40-60% compared to nighttime gas-heavy generation. GreenQueue exploits this gap.

## How It Works

```
User submits job  -->  ML model forecasts next 24h of carbon intensity
                  -->  Scheduler finds top-3 greenest windows
                  -->  User picks a window (or accepts the best)
                  -->  Background executor runs the job at the optimal time
                  -->  Impact dashboard shows CO2 saved vs naive execution
```

## Architecture

```
frontend/                   # Vanilla HTML/CSS/JS SPA
  index.html                # 4-page layout: Dashboard, Schedule, Jobs, Impact
  style.css                 # Professional dark theme with CSS animations
  app.js                    # Canvas charts, API calls, toast notifications

backend/
  server.py                 # FastAPI app — all routes + background executor
  database.py               # SQLAlchemy async ORM (SQLite)
  model.py                  # GradientBoostingRegressor (scikit-learn)
  scheduler.py              # Sliding-window green-time optimizer
  mock_energy.py            # Realistic mock carbon data generator
  seed_data.py              # Historical data seeder (4300+ rows)
  data/greenqueue.db        # SQLite database
  forecaster_model.pkl      # Trained ML model
```

## Features

- **ML Forecasting** — GradientBoostingRegressor trained on historical data predicts next-24h carbon intensity (MAE ~24 gCO2/kWh)
- **Smart Scheduler** — Sliding-window algorithm finds top-3 lowest-carbon execution windows for any job duration
- **Background Executor** — Async loop transitions jobs through `scheduled -> running -> completed` based on time
- **Impact Dashboard** — Side-by-side comparison of smart vs naive carbon, cumulative savings tracker
- **Carbon Heatmap** — Hour-of-day x day-of-week visualization of grid intensity patterns
- **Demo Mode** — One-click demo data seeding for hackathon presentations

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, FastAPI, uvicorn |
| Database | SQLAlchemy (async) + aiosqlite + SQLite |
| ML | scikit-learn GradientBoostingRegressor |
| Frontend | Vanilla HTML/CSS/JS, Canvas API |
| Data | Mock generator with realistic diurnal solar/wind patterns |

## Quick Start

```bash
# 1. Clone and enter project
cd CheeseHacks2026

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Seed historical data
cd backend
python seed_data.py

# 5. Start the server
python server.py
```

Open **http://localhost:8000** in your browser.

### First-time setup

1. Click **Dashboard** — view current carbon intensity and energy mix
2. The ML model auto-trains on first forecast request, or hit `POST /api/forecast/train`
3. Click **Seed Demo Data** in the sidebar to populate sample jobs
4. Visit **Schedule** to submit new jobs and pick green windows
5. Check **Impact** to see how much CO2 you saved

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/energy/current` | Current carbon intensity + energy mix |
| GET | `/api/energy/history` | Historical readings from DB |
| GET | `/api/energy/stats` | Aggregate stats (24h, 7d, all-time) |
| GET | `/api/energy/heatmap` | Hour x day-of-week intensity matrix |
| POST | `/api/forecast/train` | Train ML model |
| GET | `/api/forecast/next24h` | 24h carbon predictions |
| POST | `/api/jobs/suggest` | Submit job, get green window suggestions |
| POST | `/api/jobs/schedule` | Accept a window and schedule job |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/jobs/stats` | Job statistics |
| GET | `/api/jobs/impact` | Smart vs naive comparison data |
| POST | `/api/demo/seed` | Create 5 sample demo jobs |

---

*Built with care for the planet at CheeseHacks 2026.*

