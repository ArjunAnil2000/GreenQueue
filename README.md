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
git clone https://github.com/ArjunAnil2000/GEAS.git
cd GEAS

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install psutil
pip install -r backend/requirements.txt

# 4. Seed historical data
cd backend
python seed_data.py

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

*Built with care for the planet at CheeseHacks 2026.*

