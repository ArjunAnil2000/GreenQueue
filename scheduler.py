import os
import signal
import time
import sys
import subprocess
import psutil
import threading
import shlex
import sqlite3
import datetime
import argparse
from collections import deque

class Task:
    def __init__(self, name, cmd, initial_i=1.0, job_id=None, nice_value=0):
        self.name = name
        self.cmd = cmd
        self.pid = None
        self.proc = None
        self.popen = None
        self.i = initial_i
        self.is_running = False
        # job_id determines if this task syncs back to the DB. 
        # CLI tasks default to None and are ignored by DB sync.
        self.job_id = job_id 
        self.nice_value = nice_value # Store the assigned nice value

    def start(self):
        if self.pid is None:
            try:
                self.popen = subprocess.Popen(
                    shlex.split(self.cmd),
                    start_new_session=True,
                )
                self.pid = self.popen.pid
                self.proc = psutil.Process(self.pid)
                self.proc.cpu_percent(interval=None)

                try:
                    self.proc.nice(self.nice_value)
                except psutil.AccessDenied:
                    pass
            except Exception as e:
                print(f"[ERROR] Could not start task '{self.name}'. Command '{self.cmd}' failed: {e}")
                self.is_running = False
        else:
            os.killpg(os.getpgid(self.pid), signal.SIGCONT)
            self.proc.cpu_percent(interval=None)
            for child in self.proc.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)
                except psutil.NoSuchProcess:
                    pass

        self.is_running = True
        print(f"[START/RESUME] Task {self.name} (PID: {self.pid}) | Command: {self.cmd} | Nice: {self.nice_value}")

    def pause(self):
        if self.pid and self.is_running:
            os.killpg(os.getpgid(self.pid), signal.SIGSTOP)
            self.is_running = False
            print(f"[PAUSE] Task {self.name} (PID: {self.pid}) stopped. I={self.i:.2f}")

class GEASScheduler:
    def __init__(self, db_path=None, k=1.0, alpha=0.7, zone='US-CAL-CISO'):
        self.k = k
        self.alpha = alpha
        self.queue = deque()
        self.running_tasks = []
        self.current_gi = 10.0
        self.ti = 0.0
        self.num_cores = psutil.cpu_count(logical=True)
        self.lock = threading.Lock()
        
        self.db_path = db_path
        self.last_fetched_hour = None
        self.zone = zone
        self.pending_completions = set()

    def submit_task(self, task):
        with self.lock:
            print(f"[SUBMIT] New task added to queue: {task.name} | Command: {task.cmd}")
            self.queue.append(task)

    def update_gi(self, new_gi):
        with self.lock:
            print(f"\n[GI UPDATE] Greenness Index changed from {self.current_gi} to {new_gi}")
            self.current_gi = new_gi

    def try_fetch_gi(self):
        if not self.db_path:
            return False
        now = datetime.datetime.now(datetime.UTC)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        if self.last_fetched_hour == current_hour:
            return True

        target_timestamp = current_hour.strftime('%Y-%m-%d %H:00:00.000000')
        thirty_days_ago = (current_hour - datetime.timedelta(days=30)).strftime('%Y-%m-%d %H:00:00.000000')

        try:
            conn = sqlite3.connect(self.db_path, timeout=1.0)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT carbon_intensity FROM carbon_readings WHERE timestamp = ? AND zone = ?",
                (target_timestamp, self.zone)
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return False
            
            current_carbon = row[0]
            cursor.execute(
                "SELECT MIN(carbon_intensity), MAX(carbon_intensity) FROM carbon_readings WHERE timestamp >= ? AND zone = ?",
                (thirty_days_ago, self.zone)
            )
            min_carbon, max_carbon = cursor.fetchone()
            conn.close()

            if min_carbon is None or max_carbon is None:
                min_carbon, max_carbon = current_carbon, current_carbon
            
            if max_carbon == min_carbon:
                gi = 5.0
            else:
                clamped = max(min_carbon, min(current_carbon, max_carbon))
                ratio = (clamped - min_carbon) / (max_carbon - min_carbon)
                gi = (1.0 - ratio) * 10.0
            
            self.update_gi(round(gi, 2))
            self.last_fetched_hour = current_hour
            print(f"[DB] Fetched GI: {round(gi, 2)} for zone {self.zone}")
            return True
        except Exception:
            return False

    def sync_db_jobs(self):
        if not self.db_path:
            return

        now = datetime.datetime.now(datetime.UTC)
        
        # 1. Precise timestamp for writing completion records
        now_str = now.strftime('%Y-%m-%d %H:%M:%S.%f')
        
        try:
            conn = sqlite3.connect(self.db_path, timeout=1.0)
            cursor = conn.cursor()
            
            # Flush DB jobs that have completed using the precise timestamp
            if self.pending_completions:
                for jid in list(self.pending_completions):
                    cursor.execute(
                        "UPDATE jobs SET status = 'completed', completed_at = ? WHERE id = ?",
                        (now_str, jid)
                    )
                conn.commit()
                self.pending_completions.clear()
                print("[DB] Successfully flushed completed jobs to database.")
            
            # Poll for new scheduled jobs using the minute-truncated timestamp
            cursor.execute(
                "SELECT id, name, command FROM jobs WHERE status = 'scheduled' AND scheduled_start <= ?",
                (now_str,)
            )
            jobs = cursor.fetchall()
            
            for job in jobs:
                job_id, name, command_str = job
                
                # Mark as queued to prevent duplicate fetching
                cursor.execute("UPDATE jobs SET status = 'queued' WHERE id = ?", (job_id,))
                conn.commit()
                
                # Ensure we have a fallback if the command is somehow empty in the DB
                actual_cmd = command_str if command_str else f"echo 'Warning: Empty command in DB for job {job_id}'"
                
                print(f"[DB] Job '{name}' (ID: {job_id}) scheduled start arrived.")
                new_task = Task(name=f"{name}_#{job_id}", cmd=actual_cmd, job_id=job_id)
                self.submit_task(new_task)

            conn.close()
        except sqlite3.OperationalError as e:
            print(f"[DB] Locked during job sync: {e}. Retrying next minute...")
        except Exception as e:
            print(f"[DB] Error syncing jobs: {e}")

    def measure_actual_intensiveness(self, task):
        if not task.is_running or task.proc is None:
            return 0.0
        try:
            all_procs = [task.proc]
            for child in task.proc.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)
                    all_procs.append(child)
                except psutil.NoSuchProcess:
                    pass
            task.proc.cpu_percent(interval=None)
            time.sleep(5)
            total_raw_cpu = 0.0
            for p in all_procs:
                try: total_raw_cpu += p.cpu_percent(interval=None)
                except psutil.NoSuchProcess: pass
            measured_i = (total_raw_cpu / (self.num_cores * 100.0)) * 10.0
            return min(max(measured_i, 0.0), 10.0)
        except psutil.NoSuchProcess:
            return 0.0

    def tick_minute(self):
        self.try_fetch_gi()
        self.sync_db_jobs() 
        
        with self.lock:
            print(f"\n--- Minute Tick | GI: {self.current_gi} | Capacity: {self.k * self.current_gi:.2f} ---")
            self.ti = 0.0
            active_tasks = []
            
            for t in self.running_tasks:
                if t.popen is not None and t.popen.poll() is not None:
                    print(f"[CLEANUP] Task {t.name} (PID: {t.pid}) finished with exit code {t.popen.returncode}. Reaped.")
                    t.is_running = False
                    
                    if t.job_id is not None:
                        self.pending_completions.add(t.job_id)

                elif t.proc and t.proc.is_running() and t.proc.status() != psutil.STATUS_ZOMBIE:
                    active_tasks.append(t)
                else:
                    print(f"[CLEANUP] Task {t.name} (PID: {t.pid}) died unexpectedly or became a zombie.")
                    t.is_running = False
                    
                    if t.job_id is not None:
                        self.pending_completions.add(t.job_id)
                    
            self.running_tasks = active_tasks
            
            for task in self.running_tasks:
                actual_i = self.measure_actual_intensiveness(task)
                task.i = (1 - self.alpha) * task.i + (self.alpha * actual_i)
                print(f"[STATUS] PID={task.pid}, I_t={actual_i:.1f}, I_EWMA={task.i:.2f}")
                self.ti += task.i

            print(f"[STATUS] Current TI: {self.ti:.2f}")
            
            tasks_to_evict = [t for t in self.running_tasks if t.i > self.current_gi]
            for t in tasks_to_evict:
                t.pause()
                self.running_tasks.remove(t)
                self.queue.append(t)
                self.ti -= t.i
                print(f"[PREEMPT] Task {t.name} exceeded current GI ({t.i:.2f} > {self.current_gi:.2f}). Evicted.")

            capacity = self.k * self.current_gi
            
            while self.ti >= capacity and self.running_tasks:
                heaviest_task = max(self.running_tasks, key=lambda t: t.i)
                heaviest_task.pause()
                self.running_tasks.remove(heaviest_task)
                self.queue.append(heaviest_task)
                self.ti -= heaviest_task.i
                print(f"[PREEMPT] Evicted {heaviest_task.name}. New TI: {self.ti:.2f}")

            system_cpu_usage = psutil.cpu_percent(interval=None)
            print(f"[STATUS] System CPU: {system_cpu_usage:.1f}%")

            tasks_to_requeue = []
            while self.queue:
                if system_cpu_usage > 90.0:
                    print(f"[ADMISSION] System CPU at {system_cpu_usage:.1f}% (> 90%). Halting admissions this tick.")
                    break

                next_task = self.queue.popleft()
                
                if next_task.i > self.current_gi:
                    tasks_to_requeue.append(next_task)
                    continue
                    
                if self.ti + next_task.i < capacity:
                    next_task.start()
                    self.running_tasks.append(next_task)
                    self.ti += next_task.i
                else:
                    tasks_to_requeue.append(next_task)
                    break
                    
            for t in reversed(tasks_to_requeue):
                self.queue.appendleft(t)

            num_running = len(self.running_tasks)
            if num_running > 0:
                step = 19.0 / max(1, num_running - 1) if num_running > 1 else 0
                for index, t in enumerate(self.running_tasks):
                    calculated_nice = int(min(19, round(index * step)))
                    if t.proc and t.nice_value != calculated_nice:
                        try:
                            t.proc.nice(calculated_nice)
                            t.nice_value = calculated_nice
                            print(f"[PRIORITY] Re-niced {t.name} to {calculated_nice}")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

    def run_scheduler_loop(self):
        print("[DAEMON] Scheduler loop started.")
        while True:
            try:
                self.tick_minute()
            except Exception as e:
                # Catch the error, log it, but KEEP THE LOOP ALIVE
                print(f"[CRITICAL] Scheduler tick encountered an error: {e}")
            
            time.sleep(10) # Testing interval (change to 60 for prod)

    def shutdown(self):
        print("\nShutting down scheduler... Aborting all tasks...")
        with self.lock:
            while self.queue:
                task = self.queue.popleft()
                if task.pid:
                    try: os.killpg(os.getpgid(task.pid), signal.SIGTERM)
                    except (ProcessLookupError, OSError): pass
            for t in self.running_tasks:
                try: os.killpg(os.getpgid(t.pid), signal.SIGTERM)
                except (ProcessLookupError, OSError): pass
        print("All tasks have been terminated. Goodbye!")


def interactive_cli(scheduler, default_initial_i):
    print("\n🌲 Welcome to the Tree-VDF Green Scheduler CLI 🌲")
    print("Commands:")
    print("  submit <name> \"<command>\" [initial_i]  - Submit a new task (CLI jobs do not sync to DB)")
    print("  gi <value>                             - Update Greenness Index (0-10) manually")
    print("  status                                 - View current queue and running tasks")
    print("  exit                                   - Kill all tasks and shutdown")
    
    while True:
        try:
            user_input = input("\ntree-vdf> ").strip()
            if not user_input: continue
                
            parts = shlex.split(user_input)
            cmd = parts[0].lower()

            if cmd in ['exit', 'quit']:
                scheduler.shutdown()
                break
            elif cmd == 'submit':
                if len(parts) >= 3:
                    name = parts[1]
                    command = parts[2]
                    initial_i = float(parts[3]) if len(parts) > 3 else default_initial_i
                    
                    # Note: job_id is deliberately left as None here to keep CLI pure
                    scheduler.submit_task(Task(name, command, initial_i))
                else:
                    print(f"Usage: submit <name> \"<command>\" [initial_i]")
            elif cmd == 'gi':
                if len(parts) == 2: scheduler.update_gi(float(parts[1]))
                else: print("Usage: gi <0-10>")
            elif cmd == 'status':
                with scheduler.lock:
                    print(f"\n[SYSTEM STATUS] GI: {scheduler.current_gi} | Capacity: {scheduler.k * scheduler.current_gi:.2f} | Current TI: {scheduler.ti:.2f}")
                    print("--- Running Tasks ---")
                    for t in scheduler.running_tasks: print(f"  - {t.name} (PID: {t.pid}, I: {t.i:.2f})")
                    print("--- Queued Tasks ---")
                    for t in scheduler.queue: print(f"  - {t.name} (Initial I: {t.i:.2f}, Paused: {bool(t.pid)})")
            else:
                print(f"Unknown command: {cmd}")
        except Exception as e: print(f"CLI Error: {e}")
        except KeyboardInterrupt:
            scheduler.shutdown()
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tree-VDF Green Energy Scheduler")
    parser.add_argument("--db", type=str, help="Path to the carbon readings SQLite database", default="./backend/data/greenqueue.db")
    parser.add_argument("--k", type=float, help="System capacity multiplier (k)", default=2.0)
    parser.add_argument("--alpha", type=float, help="EWMA smoothing factor (alpha)", default=0.7)
    parser.add_argument("--initial_i", type=float, help="Default initial intensiveness for tasks", default=1.0)
    parser.add_argument("--zone", type=str, help="The grid zone to fetch carbon readings for", default="US-CAL-CISO")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive CLI mode")
    parser.add_argument("--log", type=str, help="Path to log file (used in daemon mode)", default="./scheduler.log")
    
    args = parser.parse_args()

    if not args.interactive:
        log_fd = open(args.log, "a", buffering=1)
        sys.stdout = log_fd
        sys.stderr = log_fd

    print("=========================================")
    print("🌲 Starting Tree-VDF Green Scheduler 🌲")
    print("=========================================")
    for key, value in vars(args).items(): print(f"  {key}: {value}")
    print(f"  Mode: {'Interactive CLI' if args.interactive else 'Daemon (Background)'}")
    print("=========================================\n")

    scheduler = GEASScheduler(db_path=args.db, k=args.k, alpha=args.alpha, zone=args.zone)

    def signal_handler(signum, frame):
        print(f"\n[SYSTEM] Received signal {signum}, initiating graceful shutdown...")
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.interactive:
        scheduler_thread = threading.Thread(target=scheduler.run_scheduler_loop, daemon=True)
        scheduler_thread.start()
        interactive_cli(scheduler, default_initial_i=args.initial_i)
    else:
        print("[DAEMON] Scheduler running in background. Waiting for events...")
        scheduler.run_scheduler_loop()
