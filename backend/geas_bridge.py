"""
geas_bridge.py — Bridge between the root GEAS scheduler and the FastAPI web app.

Wraps the Task + GEASScheduler concepts from scheduler.py as a singleton with
DB-sync hooks.  Runs the scheduler loop in a daemon thread; the FastAPI async
world interacts through thread-safe methods.
"""

import os
import signal
import time
import subprocess
import shlex
import threading
import platform
from collections import deque
from datetime import datetime, timezone

import psutil


# ─── WebTask ────────────────────────────────────────────────────────────────
class WebTask:
    """OS-process wrapper with GEAS lifecycle (start / pause / resume)."""

    def __init__(self, job_id: int, name: str, cmd: str, initial_i: float = 1.0):
        self.job_id = job_id
        self.name = name
        self.cmd = cmd
        self.pid: int | None = None
        self.proc: psutil.Process | None = None
        self.popen: subprocess.Popen | None = None
        self.i: float = initial_i          # EWMA intensity (0-10 scale)
        self.is_running: bool = False
        self.exit_code: int | None = None
        self.finished: bool = False
        self.started_at: datetime | None = None
        self.carbon_samples: list[float] = []   # carbon intensity readings while running

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        if self.pid is None:
            self.popen = subprocess.Popen(
                shlex.split(self.cmd),
                start_new_session=True,
            )
            self.pid = self.popen.pid
            self.proc = psutil.Process(self.pid)
            self.proc.cpu_percent(interval=None)          # prime
            self.started_at = datetime.now(timezone.utc)
        else:
            # Resuming from pause → SIGCONT the whole process group
            os.killpg(os.getpgid(self.pid), signal.SIGCONT)
            self.proc.cpu_percent(interval=None)
            for child in self.proc.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)
                except psutil.NoSuchProcess:
                    pass
        self.is_running = True

    def pause(self):
        if self.pid and self.is_running:
            os.killpg(os.getpgid(self.pid), signal.SIGSTOP)
            self.is_running = False

    def terminate(self):
        if self.pid:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass


# ─── GEASBridge (singleton) ────────────────────────────────────────────────
class GEASBridge:
    """Green Energy-Aware Scheduler bridge for the web app."""

    _instance: "GEASBridge | None" = None

    @classmethod
    def get(cls) -> "GEASBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, k: float = 2.0, alpha: float = 0.3):
        self.k = k                           # capacity multiplier
        self.alpha = alpha                    # EWMA smoothing
        self.queue: deque[WebTask] = deque()  # tasks waiting to run
        self.running_tasks: list[WebTask] = []
        self.all_tasks: dict[int, WebTask] = {}         # job_id → task (active)
        self.finished_tasks: dict[int, WebTask] = {}    # job_id → task (done)
        self.current_gi: float = 5.0
        self.ti: float = 0.0
        self.num_cores: int = psutil.cpu_count(logical=True) or 4
        self.lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        # Status changes to sync back to DB, list of (job_id, status, extra_dict)
        self._changes: list[tuple[int, str, dict]] = []
        self._current_carbon: float = 0.0      # latest grid carbon intensity

    # -- public API ----------------------------------------------------------
    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            print("[GEAS] Scheduler thread started")

    def stop(self):
        self._running = False
        self._shutdown_all()

    def submit(self, job_id: int, name: str, cmd: str, initial_i: float = 1.0) -> WebTask:
        task = WebTask(job_id, name, cmd, initial_i)
        with self.lock:
            self.all_tasks[job_id] = task
            self.queue.append(task)
            self._changes.append((job_id, "queued", {}))
        print(f"[GEAS] Submitted: {name} (job #{job_id})")
        return task

    def update_gi(self, new_gi: float, carbon_intensity: float = 0.0):
        with self.lock:
            old = self.current_gi
            self.current_gi = max(0.5, min(10.0, new_gi))
            self._current_carbon = carbon_intensity
            # Record carbon sample for every running task
            for t in self.running_tasks:
                t.carbon_samples.append(carbon_intensity)
            if abs(old - self.current_gi) > 0.3:
                print(f"[GEAS] GI {old:.1f} → {self.current_gi:.1f}  "
                      f"(capacity {self.k * self.current_gi:.1f})")

    def cancel(self, job_id: int) -> bool:
        with self.lock:
            for t in self.running_tasks:
                if t.job_id == job_id:
                    t.terminate()
                    self.running_tasks.remove(t)
                    self.ti -= t.i
                    self.all_tasks.pop(job_id, None)
                    return True
            for t in list(self.queue):
                if t.job_id == job_id:
                    if t.pid:
                        t.terminate()
                    self.queue.remove(t)
                    self.all_tasks.pop(job_id, None)
                    return True
        return False

    def pop_changes(self) -> list[tuple[int, str, dict]]:
        with self.lock:
            out = self._changes[:]
            self._changes.clear()
            return out

    def snapshot(self) -> dict:
        """Return a thread-safe snapshot of scheduler state."""
        with self.lock:
            return {
                "gi": round(self.current_gi, 2),
                "capacity": round(self.k * self.current_gi, 2),
                "ti": round(self.ti, 2),
                "running": [
                    {"job_id": t.job_id, "name": t.name, "pid": t.pid,
                     "intensity": round(t.i, 2)}
                    for t in self.running_tasks
                ],
                "queued": [
                    {"job_id": t.job_id, "name": t.name,
                     "paused": t.pid is not None}
                    for t in self.queue
                ],
            }

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def carbon_to_gi(carbon_intensity: float) -> float:
        """Lower carbon → higher GI.  Typical US range 100-500 gCO₂/kWh."""
        gi = 10.0 * (1.0 - carbon_intensity / 500.0)
        return max(0.5, min(10.0, gi))

    # -- internal scheduler --------------------------------------------------
    def _measure(self, task: WebTask) -> float:
        if not task.is_running or task.proc is None:
            return 0.0
        try:
            procs = [task.proc]
            for c in task.proc.children(recursive=True):
                try:
                    c.cpu_percent(interval=None)
                    procs.append(c)
                except psutil.NoSuchProcess:
                    pass
            task.proc.cpu_percent(interval=None)
            time.sleep(2)                                    # short window
            total = sum(
                p.cpu_percent(interval=None)
                for p in procs
                if p.is_running()
            )
            return max(0.0, min(10.0, (total / (self.num_cores * 100)) * 10))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0

    def _tick(self):
        # 1. Reap finished processes (under lock)
        with self.lock:
            alive = []
            for t in self.running_tasks:
                if t.popen is not None and t.popen.poll() is not None:
                    t.exit_code = t.popen.returncode
                    t.is_running = False
                    t.finished = True
                    self.finished_tasks[t.job_id] = t
                    self.all_tasks.pop(t.job_id, None)
                    status = "completed" if t.exit_code == 0 else "failed"
                    avg_c = sum(t.carbon_samples) / len(t.carbon_samples) if t.carbon_samples else 0
                    self._changes.append((t.job_id, status, {
                        "exit_code": t.exit_code, "pid": t.pid,
                        "avg_carbon": round(avg_c, 1),
                    }))
                    print(f"[GEAS] {t.name} finished (exit={t.exit_code}, avg_carbon={avg_c:.1f})")
                elif t.proc and t.proc.is_running() and t.proc.status() != psutil.STATUS_ZOMBIE:
                    alive.append(t)
                else:
                    t.is_running = False
                    t.finished = True
                    t.exit_code = -1
                    self.finished_tasks[t.job_id] = t
                    self.all_tasks.pop(t.job_id, None)
                    avg_c = sum(t.carbon_samples) / len(t.carbon_samples) if t.carbon_samples else 0
                    self._changes.append((t.job_id, "failed", {
                        "exit_code": -1, "pid": t.pid,
                        "avg_carbon": round(avg_c, 1),
                    }))
                    print(f"[GEAS] {t.name} died unexpectedly")
            self.running_tasks = alive
            to_measure = list(self.running_tasks)

        # 2. Measure CPU intensities (outside lock — involves sleep)
        readings: dict[int, float] = {}
        for t in to_measure:
            readings[t.job_id] = self._measure(t)

        # 3. Update EWMA + preempt / promote (under lock)
        with self.lock:
            self.ti = 0.0
            for t in self.running_tasks:
                if t.job_id in readings:
                    t.i = (1 - self.alpha) * t.i + self.alpha * readings[t.job_id]
                self.ti += t.i

            capacity = self.k * self.current_gi

            # Preempt heaviest if over capacity
            while self.ti >= capacity and self.running_tasks:
                heavy = max(self.running_tasks, key=lambda x: x.i)
                heavy.pause()
                self.running_tasks.remove(heavy)
                self.queue.append(heavy)
                self.ti -= heavy.i
                self._changes.append((heavy.job_id, "paused", {"pid": heavy.pid}))
                print(f"[GEAS] Preempted {heavy.name} (I={heavy.i:.2f})")

            # Promote from queue while capacity available
            while self.queue:
                nxt = self.queue[0]
                if self.ti + nxt.i < capacity:
                    self.queue.popleft()
                    nxt.start()
                    self.running_tasks.append(nxt)
                    self.ti += nxt.i
                    self._changes.append((nxt.job_id, "running",
                                          {"pid": nxt.pid, "started_at": nxt.started_at}))
                    print(f"[GEAS] Started/Resumed {nxt.name} (PID={nxt.pid})")
                else:
                    break

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                print(f"[GEAS] tick error: {e}")
            time.sleep(10)

    def _shutdown_all(self):
        with self.lock:
            for t in list(self.queue):
                t.terminate()
            for t in self.running_tasks:
                t.terminate()
            self.queue.clear()
            self.running_tasks.clear()
        print("[GEAS] All tasks terminated")
