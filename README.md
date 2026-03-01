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
git clone https://github.com/ArjunAnil2000/GEAS.git
cd GEAS

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
# 5.1 Open a tmux window
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

## The Tree-VDF Green Scheduler (`scheduler.py`)

While the backend API handles user requests and ML forecasting, `scheduler.py` is the workhorse engine that actually executes the jobs on the host machine. It is a custom, carbon-aware process scheduler that actively monitors running tasks and dynamically pauses, resumes, or reprioritizes them based on the real-time Greenness Index (GI).

### 1. Starting the Scheduler
The scheduler runs independently of the web server. You can run it as a silent background daemon (which syncs jobs from the SQLite database) or in Interactive CLI mode for testing.

**Run in Interactive Mode (Recommended for testing/demoing):**
`bash
python scheduler.py --interactive
`

**Run in Daemon Mode (Production):**
`bash
python scheduler.py --db ./backend/data/greenqueue.db --log ./scheduler.log
`

**Available Arguments:**
* `--interactive`: Launches the interactive command-line interface.
* `--db`: Path to the SQLite database to sync web-submitted jobs (default: `./backend/data/greenqueue.db`).
* `--k`: System capacity multiplier (default: `2.0`).
* `--alpha`: EWMA smoothing factor for calculating CPU intensiveness (default: `0.7`).
* `--zone`: The electrical grid zone to fetch carbon data for (default: `US-CAL-CISO`).
* `--initial_i`: Default initial intensiveness for tasks (default: `1.0`).

### 2. Interactive CLI Commands
When running with `--interactive`, you can manually submit tasks and manipulate the grid's "greenness" to watch the scheduler react in real-time.

* `submit <name> "<command>" [initial_i]`: Submits a new local task to the queue. *(Note: CLI tasks do not sync back to the web DB).*
    * *Example:* `submit burn "python -c 'while True: pass'"`
* `gi <value>`: Manually overrides the current Greenness Index (0.0 to 10.0) to simulate sudden grid changes.
    * *Example:* `gi 3.5` (Simulates a sudden drop in renewable energy).
* `status`: Prints the current GI, system capacity, and a live breakdown of all running and queued tasks.
* `exit`: Safely terminates all running tasks and shuts down the scheduler.

### 3. Under the Hood: Smart Resource Management
This isn't just a simple FIFO queue; it uses advanced OS-level process management:

* **Dynamic Re-Nicing:** To prevent new tasks from starving older ones, the scheduler dynamically recalculates and applies Linux `nice` values (priority levels 0-19) to all running tasks every minute. Older tasks get the lion's share of the CPU.
* **Carbon Preemption:** If a task's measured CPU intensiveness exceeds the current grid Greenness Index (I > GI), the scheduler sends a `SIGSTOP` signal to pause it, requeues it, and waits for a greener time to send `SIGCONT`.
* **System Overload Protection:** It monitors global CPU usage using `psutil`. If the system-wide load exceeds 90%, it halts all new admissions to prevent machine lockups.

### The Algorithm: Heuristics & Sustainability

The Tree-VDF Green Scheduler doesn't just blindly queue tasks. It acts as a real-time bridge between operating system resource management and the physical electrical grid. 



To do this, it continuously calculates and compares three core metrics:
* **GI (Greenness Index):** A real-time score from `0.0` to `10.0` representing how clean the local power grid is (10 = highest renewable energy saturation).
* **I (Task Intensiveness):** A score from `0.0` to `10.0` measuring how heavily a specific background task is utilizing the CPU cores. 
* **TI (Total Intensiveness):** The sum of all currently running tasks' `I` scores.

#### The Scheduling Rules
Every 60 seconds, the scheduler evaluates the system against these strict heuristic rules:

1. **The Golden Rule of Sustainability ($I \le GI$):** A task is only allowed to run if the grid is "green enough" to support its CPU demands. If a task's Intensiveness (`I`) exceeds the current Greenness Index (`GI`), the task is immediately paused (`SIGSTOP`) and evicted back to the queue. Heavy tasks *must* wait for green grid hours.
2. **Dynamic System Capacity ($TI < k \times GI$):** The total allowed compute load on the machine expands and contracts with the grid. The maximum allowed capacity is `k * GI` (where `k` is a user-defined multiplier, default `2.0`). If a sudden drop in solar/wind power causes the `GI` to plummet, the system capacity shrinks. If $TI$ exceeds this new lower capacity, the scheduler pauses the heaviest running tasks until the system fits within the green budget.
3. **EWMA CPU Smoothing:** To prevent tasks from being unfairly paused due to momentary split-second CPU spikes, the scheduler calculates Task Intensiveness (`I`) using an Exponentially Weighted Moving Average (EWMA). This smooths out the measurements over time, allowing for realistic sustained workload evaluations.

#### Why This Matters for Sustainability
Data centers and heavy compute jobs (like ML training, video rendering, or batch processing) are massive energy sinks. Naive schedulers run these jobs the exact millisecond they are submitted, even if the local grid is currently burning coal or natural gas to meet peak evening demand. 

By strictly enforcing **Capacity = $k \times GI$**, GreenQueue physically forces non-urgent compute workloads to execute during off-peak, high-renewable windows (like sunny afternoons with high solar output or windy nights). This actively reduces the actual carbon footprint of the software without requiring the developer to change a single line of their processing code.

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
| `POST` | `/api/geas/submit` | Submit a shell command to GEAS |
| `GET` | `/api/geas/status` | GEAS scheduler snapshot (GI, capacity, queued) |

---

## The Science

### Carbon Intensity

Carbon intensity measures how many grams of CO₂ are emitted per kilowatt-hour of electricity generated. It varies based on the fuel mix:

| Fuel | Emission Factor (gCO₂/kWh) |
|------|-----------------------------|
| Coal | 1,000 |
| Natural Gas | 450 |
| Nuclear | 12 |
| Solar | 0 |
| Wind | 0 |
| Hydro | 0 |

When solar and wind contribute a larger share, the weighted average drops significantly. GreenQueue forecasts these fluctuations and schedules jobs to coincide with the cleanest periods.

### GPU Energy Model

GreenQueue uses a simplified but representative energy model:

$$E_{kWh} = \frac{P_{TDP} \times N_{GPUs} \times T_{hours}}{1000}$$

Where $P_{TDP}$ = 300W (A100-class GPU), $N_{GPUs}$ is user-specified (1–1000), and $T_{hours}$ = 1 (per job run).

$$CO_2\text{ (grams)} = CI_{gCO_2/kWh} \times E_{kWh}$$

The savings are then: $\Delta CO_2 = CO_{2,naive} - CO_{2,smart}$

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">

*Built with care for the planet at CheeseHacks 2026, University of Wisconsin–Madison.*

**Every watt-hour counts. Every hour matters.**

</div>

