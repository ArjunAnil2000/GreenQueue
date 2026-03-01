<div align="center">

# GreenQueue

### Carbon-Aware AI Job Scheduler

**CheeseHacks 2026** — University of Wisconsin–Madison

*Shift compute to when the grid is cleanest. Save carbon without changing a single line of your code.*

</div>

---

## Why GreenQueue?

Google has committed to operating on **24/7 carbon-free energy by 2030**. Microsoft aims to be **carbon negative** by the same year. These are ambitious goals but sustainability is not just the responsibility of hyperscale cloud providers. It is the responsibility of **every individual** who deploys a model, runs a pipeline, or kicks off a batch job.

Until Google, AWS, and Azure achieve fully carbon-free infrastructure, there is a gap: **the grid that powers our compute still burns fossil fuels**, and the carbon intensity of that grid varies dramatically hour to hour. During midday solar peaks, a US grid region might emit as little as 150 gCO₂/kWh. At 2 AM when gas turbines dominate, that same region can spike past 400 gCO₂/kWh. Most workloads (training runs, ETL pipelines, batch inference) are scheduled without any awareness of this gap.

**GreenQueue closes that gap.** It is a carbon-aware job scheduler that combines real-time grid data from the US Energy Information Administration (EIA), a machine learning forecasting model, and a GPU-aware energy calculator to find the greenest window for your workload. Users tell GreenQueue how long they can wait; GreenQueue tells them exactly when to run.

> The average ML training job on 8× A100 GPUs consumes ~2.4 kWh per hour. Shifting that job by just 4 hours can save **200+ grams of CO₂**, the equivalent of driving a car 0.5 miles. Scale that across thousands of daily jobs in a research cluster or cloud tenant, and the numbers become significant.

---

## Team

| Name | Role |
|------|------|
| **Arjun Anil** | Backend / Scheduler |
| **Chenglong Yu** | Data Engineering / Scheduler |
| **Shivansh Gupta** | Full-Stack / System Architecture / ML |
| **Sudhi Sharma** | API Integration / Data Visualization |

---

## How It Works

```
                          ┌──────────────────────────--┐
                          │   User submits a job       │
                          │   (name, type, priority,   │
                          │    GPU count, flexibility) │
                          └────────────┬─────────────--|
                                       │
                          ┌────────────▼─────────────--┐
                          │  ML model forecasts next   │
                          │  24h of carbon intensity   │
                          │  (GradientBoostingRegressor│
                          │   trained on EIA data)     │
                          └────────────┬─────────────--┘
                                       │
                          ┌────────────▼─────────────--┐
                          │  Scheduler scans forecast  │
                          │  within user's flexibility │
                          │  window → ranks top 3      │
                          │  greenest start times      │
                          └────────────┬─────────────--┘
                                       │
                     ┌─────────────────┼─────────────────┐
                     │                                   │
          ┌──────────▼──────────┐            ┌───────────▼──────────┐
          │  Schedule Optimally │            │   Run Immediately    │
          │  (pick a green      │            │   (accept current    │
          │   window)           │            │    carbon intensity) │
          └──────────┬──────────┘            └───────────┬──────────┘
                     │                                   │
                     └─────────────────┬─────────────────┘
                                       │
                          ┌────────────▼─────────────-┐
                          │  Background executor runs │
                          │  job at the optimal time  │
                          └────────────┬─────────────-┘
                                       │
                          ┌────────────▼─────────────-┐
                          │  Impact dashboard shows   │
                          │  CO₂ saved vs naive run   │
                          └──────────────────────────-┘
```

---

## Features

### Intelligent Scheduling

- **Green Window Finder**: User specifies how long they can wait (1–24 hours). The scheduler searches every hour within that window and returns the 3 greenest start times, ranked by carbon intensity.
- **Priority Classes**: *Latency-Critical* (need it now — get a brown-warning if the grid is dirty), *Flexible* (default — find the best window), *Batch* (scan the full 24h horizon).
- **Run Immediately**: For urgent jobs: skip the window search and run at the current intensity. GreenQueue still tracks the CO₂ cost so you can see what you "spent."

### GPU-Aware Energy Model

- **Datacenter Scale Simulation**: Slide a GPU slider from 1 to 1,000 to simulate workloads from a single dev machine to a datacenter fleet. The energy model uses A100-class TDP (300W/GPU) to estimate kWh per job.
- **CO₂ Accounting**: Every job records `co2_total_g` (actual), `co2_naive_g` (if run immediately), and `co2_saved_g` (the difference). These flow into the dashboard and impact page.

### Real-Time Grid Data

- **EIA API Integration**: Live hourly fuel-type generation data from the US Energy Information Administration. Covers coal, natural gas, nuclear, solar, wind, hydro, and battery storage.
- **Multi-Region Carbon Comparison**: Compares carbon intensity across **8 GCP cloud regions** (mapped to 7 EIA balancing authorities: MISO, PJM, ERCOT, BPAT, CISO, DUK, NEVP). Sorted greenest-first so users can pick the cleanest datacenter.
- **10-Day Backfill** — On first startup, GreenQueue fetches 10 days of historical readings to seed the ML model.

### ML Forecasting

- **GradientBoostingRegressor** (scikit-learn) trained on real EIA data.
- **Features**: hour-of-day, day-of-week, month, plus sinusoidal time encoding (`sin(2πh/24)`, `cos(2πh/24)`) to capture diurnal cycles.
- **Auto-trains** hourly as new readings arrive. Model persisted to `forecaster_model.pkl`.
- **Forecast vs Actual** overlay chart on the dashboard — so users can see how well the model is performing.

### GEAS — Live Process Scheduler

- **Green Energy-Aware Scheduler (GEAS)** — an alternative mode that manages **real OS processes** on the host machine.
- Runs as a daemon thread. Starts, pauses (`SIGSTOP`), and resumes (`SIGCONT`) actual processes based on real-time grid capacity.
- Capacity model: `capacity = k × GI`, where the Green Index (GI) is inversely proportional to current carbon intensity.
- Tracks per-task CPU intensity via `psutil` EWMA and admits/throttles tasks to stay within the green capacity envelope.

### Visualization Dashboard

- **Canvas-rendered charts** (no chart libraries) — forecast line chart with dual-line actual overlay, energy source donut, historical trend, intensity heatmap (hour × day-of-week), GCP region horizontal bars.
- **Impact Page** — grouped bar comparison of smart vs naive carbon per job, horizontal per-job savings chart, cumulative CO₂ counter.
- **Dark theme** UI with green accent, animated transitions, and toast notifications.

---

## Architecture

```
frontend/
  index.html             SPA shell — Dashboard, Job Schedule, Impact
  style.css              Dark theme, Canvas chart styling, responsive layout
  app.js                 ~1800 lines: all chart rendering, API integration, dual-mode UI

backend/
  server.py              FastAPI app — REST API, background loops, GPU energy model
  database.py            SQLAlchemy async ORM — Job, EIAReading, CarbonReading models
  scheduler.py           Green window optimizer — scans forecast horizon for greenest slots
  model.py               GradientBoostingRegressor — trains, persists, predicts 24h ahead
  geas_bridge.py         GEAS daemon — real process scheduling with carbon-aware throttling
  eia_live.py            EIA API client — fetches live fuel-type generation data
  data_source.py         Unified data layer — abstracts mock vs real data sources
  region_carbon.py       Multi-region carbon comparison across GCP zones
  gcp_regions.py         Region → EIA balancing authority mapping
  mock_energy.py         Synthetic carbon data generator (diurnal + seasonal patterns)
  config.py              Pydantic settings from .env
  data/
    greenqueue.db         SQLite database (auto-created)
    uploads/              User-uploaded demo task files
  forecaster_model.pkl   Trained ML model (auto-generated)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.13, FastAPI, uvicorn (with auto-reload) |
| **Database** | SQLAlchemy 2.0 (async) + aiosqlite + SQLite |
| **ML** | scikit-learn `GradientBoostingRegressor`, pandas, numpy |
| **Data Source** | US EIA API v2 (real-time hourly grid data) |
| **Process Mgmt** | psutil (GEAS mode — CPU monitoring + process control) |
| **HTTP Client** | httpx (async, 60s timeout for EIA calls) |
| **Frontend** | Vanilla HTML/CSS/JS, HTML5 Canvas API (zero dependencies) |

---

## Quick Start

```bash
# 1. Clone and enter project
git clone https://github.com/ArjunAnil2000/GreenQueue.git
cd GreenQueue

# 2. Create a virtual environment (Python 3.11+)
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install --upgrade pip
pip install psutil
pip install -r backend/requirements.txt
pip install python-multipart psutil

# 4. Configure environment
cp backend/.env.example backend/.env   # or create manually:
# GREENQUEUE_DATA_SOURCE=real
# EIA_API_KEY=your_eia_api_key_here

# 5. Start the server
# 5.1 Open a tmux window (if you have it installed)
tmux new -s server
python server.py
# 5.2 Use Ctrl-b + d to detach tmux window
# Use `tmux attach -t server` to attach tmux window again

# 6. Start scheduler
cd ..
python scheduler.py
```

Open **http://localhost:8000** in your browser. The app will:
- Create the SQLite database automatically
- Backfill 10 days of EIA historical data
- Train the ML model on the backfilled data
- Begin ingesting new readings every 60 seconds

### Getting an EIA API Key

1. Go to [https://www.eia.gov/opendata/register.php](https://www.eia.gov/opendata/register.php)
2. Register for a free account
3. Copy your API key into `backend/.env`

> **No API key?** Set `GREENQUEUE_DATA_SOURCE=mock` in `.env` to use the built-in synthetic data generator. All features work identically — you just see simulated carbon intensity instead of real grid data.

---

## Usage Guide

### 1. Dashboard

The landing page shows the current state of the electrical grid:
- **Current carbon intensity** and 24-hour average/low
- **ML forecast** for the next 24 hours (with actual readings overlaid)
- **Energy source breakdown** (what percentage is solar, wind, gas, etc.)
- **GCP region comparison** — see which cloud region is greenest right now

### 2. Schedule a Job

Click **+ Schedule a Job** to open the form:

| Field | Description |
|-------|-------------|
| **Job Name** | Human-readable label (e.g., "Train ResNet-50") |
| **Workload Type** | ML Training, Inference, Data Pipeline, Simulation, or General |
| **Priority Class** | Latency-Critical, Flexible, or Batch |
| **I can wait up to** | 1–24 hours — how long you're willing to delay for a greener window |
| **GPU Scale** | 1–1,000 GPUs (slider + number input) — scales the energy model |
| **Demo File** | Optional file upload for demo purposes |

Two actions are available:
- **Schedule Optimally** — finds the 3 greenest windows within your flexibility range. Pick one and the job is scheduled.
- **Run Immediately** — skip optimization and run now. The CO₂ cost is still tracked.

### 3. Impact

After jobs run, the Impact page shows:
- **Per-job CO₂ comparison** — smart scheduling vs naive (run immediately) side by side
- **Per-job savings** — horizontal bar chart showing grams of CO₂ saved per job
- **Cumulative total** — running counter of all CO₂ saved across the platform

---

## API Reference

### Energy & Grid

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Active data source and zone |
| `GET` | `/api/energy/current` | Latest carbon intensity + fuel mix |
| `GET` | `/api/energy/history?limit=168` | Historical readings (default: 7 days) |
| `GET` | `/api/energy/stats` | Aggregate statistics |
| `GET` | `/api/energy/heatmap` | Avg carbon by hour × day-of-week |
| `GET` | `/api/regions/carbon` | Live carbon comparison across 8 GCP regions |

### ML Forecast

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/forecast/train` | Retrain the ML model |
| `GET` | `/api/forecast/next24h` | 24h forecast + recent actuals |

### Jobs (Green Windows Mode)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/jobs/suggest` | Create job and get ranked green windows |
| `POST` | `/api/jobs/schedule` | Schedule job in a chosen window |
| `POST` | `/api/jobs/run-now` | Run job immediately at current intensity |
| `POST` | `/api/jobs/upload-demo` | Upload a demo task file |
| `GET` | `/api/jobs` | List all jobs (newest first) |
| `GET` | `/api/jobs/stats` | Aggregate KPIs |
| `GET` | `/api/jobs/impact` | Per-job smart vs naive CO₂ comparison |
| `DELETE` | `/api/jobs/{id}` | Remove or cancel a job |

### GEAS (Live Process Mode)

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

*Built with care for the planet at CheeseHacks 2026, University of Wisconsin–Madison.*

**Every watt-hour counts. Every hour matters.**

</div>

