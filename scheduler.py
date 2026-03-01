import os
import signal
import time
import subprocess
import psutil
import threading
import shlex
from collections import deque

class Task:
    def __init__(self, name, cmd, initial_i=1.0):
        self.name = name
        self.cmd = cmd
        self.pid = None
        self.proc = None  # Holds the psutil.Process object
        self.popen = None # Holds the subprocess.Popen object (NEW)
        self.i = initial_i
        self.is_running = False

    def start(self):
        if self.pid is None:
            # First time starting — use a new session so we can signal the
            # whole process tree (parent + children) with a single kill().
            self.popen = subprocess.Popen(
                shlex.split(self.cmd),   # no shell=True; avoids orphaned children
                start_new_session=True,  # os.setsid — gives us a process group
            )
            self.pid = self.popen.pid
            self.proc = psutil.Process(self.pid)
            # Prime cpu_percent for the parent *and* give children a moment
            # to spawn so they can be primed too.
            self.proc.cpu_percent(interval=None)
        else:
            # Resuming from a paused state — resume the ENTIRE process group
            os.killpg(os.getpgid(self.pid), signal.SIGCONT)
            # Re-prime all processes after resume
            self.proc.cpu_percent(interval=None)
            for child in self.proc.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)
                except psutil.NoSuchProcess:
                    pass

        self.is_running = True
        print(f"[START/RESUME] Task {self.name} (PID: {self.pid})")

    def pause(self):
        if self.pid and self.is_running:
            # Stop the ENTIRE process group so child workers stop too
            os.killpg(os.getpgid(self.pid), signal.SIGSTOP)
            self.is_running = False
            print(f"[PAUSE] Task {self.name} (PID: {self.pid}) stopped. I={self.i:.2f}")

class GEASScheduler:
    def __init__(self, k=1.0, alpha=0.7):
        self.k = k
        self.alpha = alpha
        self.queue = deque()
        self.running_tasks = []
        self.current_gi = 10.0
        self.ti = 0.0
        self.num_cores = psutil.cpu_count(logical=True)
        
        # Add a Threading Lock to prevent race conditions
        self.lock = threading.Lock()

    def submit_task(self, task):
        with self.lock:
            print(f"[SUBMIT] New task added to queue: {task.name}")
            self.queue.append(task)

    def update_gi(self, new_gi):
        with self.lock:
            print(f"\n[GI UPDATE] Greenness Index changed from {self.current_gi} to {new_gi}")
            self.current_gi = new_gi

    def measure_actual_intensiveness(self, task):
        """
        Measures the CPU utilization of the entire process tree
        (parent + child workers) using a single timed window, then
        maps to a 0-10 scale.
        """
        if not task.is_running or task.proc is None:
            return 0.0

        try:
            # 1. Snapshot cpu_percent for parent AND all children at once
            #    (non-blocking "prime" call that records the starting point)
            all_procs = [task.proc]
            for child in task.proc.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)   # prime each child
                    all_procs.append(child)
                except psutil.NoSuchProcess:
                    pass
            task.proc.cpu_percent(interval=None)       # prime the parent

            # 2. Wait once for the measurement window
            time.sleep(5)

            # 3. Collect cpu_percent from every process (non-blocking now)
            total_raw_cpu = 0.0
            for p in all_procs:
                try:
                    pct = p.cpu_percent(interval=None)
                    total_raw_cpu += pct
                except psutil.NoSuchProcess:
                    pass

            print(f"  [{task.name}] total raw cpu={total_raw_cpu:.1f}%  "
                  f"(procs measured: {len(all_procs)})")

            # 4. Map to 0-10 scale  (total_raw_cpu is in per-core %;
            #    e.g. 200% for 2 fully-loaded cores)
            measured_i = (total_raw_cpu / (self.num_cores * 100.0)) * 10.0
            measured_i = min(max(measured_i, 0.0), 10.0)
            print(f"  [{task.name}] measured_i={measured_i:.2f}")

            return measured_i

        except psutil.NoSuchProcess:
            return 0.0

    def tick_minute(self):
        with self.lock:
            print(f"\n--- Minute Tick | GI: {self.current_gi} | Capacity: {self.k * self.current_gi:.2f} ---")
            
            self.ti = 0.0
            
            # --- NEW CLEANUP & REAPING LOGIC ---
            active_tasks = []
            for t in self.running_tasks:
                # 1. Check if the process finished gracefully and reap the zombie
                if t.popen is not None and t.popen.poll() is not None:
                    print(f"[CLEANUP] Task {t.name} (PID: {t.pid}) finished with exit code {t.popen.returncode}. Reaped.")
                    t.is_running = False
                
                # 2. Double-check psutil status just in case it zombified another way
                elif t.proc and t.proc.is_running() and t.proc.status() != psutil.STATUS_ZOMBIE:
                    active_tasks.append(t)
                
                # 3. Catch-all for dead processes
                else:
                    print(f"[CLEANUP] Task {t.name} (PID: {t.pid}) died unexpectedly or became a zombie.")
                    t.is_running = False
                    
            self.running_tasks = active_tasks
            # -----------------------------------
            
            for task in self.running_tasks:
                actual_i = self.measure_actual_intensiveness(task)
                task.i = (1 - self.alpha) * task.i + (self.alpha * actual_i)
                print(f"[STATUS] PID={task.pid}, I_t={actual_i:.1f}, I_EWMA={task.i:.2f}")
                self.ti += task.i

            print(f"[STATUS] Current TI: {self.ti:.2f}")

            capacity = self.k * self.current_gi
            
            while self.ti >= capacity and self.running_tasks:
                heaviest_task = max(self.running_tasks, key=lambda t: t.i)
                heaviest_task.pause()
                self.running_tasks.remove(heaviest_task)
                self.queue.append(heaviest_task)
                self.ti -= heaviest_task.i
                print(f"[PREEMPT] Evicted {heaviest_task.name}. New TI: {self.ti:.2f}")

            while self.queue:
                next_task = self.queue[0]
                if self.ti + next_task.i < capacity:
                    self.queue.popleft()
                    next_task.start()
                    self.running_tasks.append(next_task)
                    self.ti += next_task.i
                else:
                    break

    def run_scheduler_loop(self):
        try:
            while True:
                self.tick_minute()
                time.sleep(10) # Note: For testing, you might want to lower this to 5 or 10 seconds
        except Exception as e:
            print(f"Scheduler loop error: {e}")

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


# --- Interactive CLI ---
def interactive_cli(scheduler):
    print("\n🌲 Welcome to the Tree-VDF Green Scheduler CLI 🌲")
    print("Commands:")
    print("  submit <name> \"<command>\" [initial_i]  - Submit a new task")
    print("  gi <value>                             - Update Greenness Index (0-10)")
    print("  status                                 - View current queue and running tasks")
    print("  exit                                   - Kill all tasks and shutdown")
    
    while True:
        try:
            # Simple prompt
            user_input = input("\ntree-vdf> ").strip()
            if not user_input:
                continue
                
            # shlex parses quotes properly, e.g., 'sleep 1000' stays together
            parts = shlex.split(user_input)
            cmd = parts[0].lower()

            if cmd in ['exit', 'quit']:
                scheduler.shutdown()
                break
                
            elif cmd == 'submit':
                if len(parts) >= 3:
                    name = parts[1]
                    command = parts[2]
                    initial_i = float(parts[3]) if len(parts) > 3 else 5.0
                    scheduler.submit_task(Task(name, command, initial_i))
                else:
                    print("Usage: submit <name> \"<command>\" [initial_i]")
                    
            elif cmd == 'gi':
                if len(parts) == 2:
                    scheduler.update_gi(float(parts[1]))
                else:
                    print("Usage: gi <0-10>")
                    
            elif cmd == 'status':
                with scheduler.lock:
                    print(f"\n[SYSTEM STATUS] GI: {scheduler.current_gi} | Capacity: {scheduler.k * scheduler.current_gi:.2f} | Current TI: {scheduler.ti:.2f}")
                    print("--- Running Tasks ---")
                    for t in scheduler.running_tasks:
                        print(f"  - {t.name} (PID: {t.pid}, I: {t.i:.2f})")
                    print("--- Queued Tasks ---")
                    for t in scheduler.queue:
                        print(f"  - {t.name} (Initial I: {t.i:.2f}, Paused: {bool(t.pid)})")
                        
            else:
                print(f"Unknown command: {cmd}")
                
        except Exception as e:
            print(f"CLI Error: {e}")
        except KeyboardInterrupt:
            # Catch Ctrl+C in the CLI
            scheduler.shutdown()
            break

if __name__ == "__main__":
    scheduler = GEASScheduler(k=2.0, alpha=0.3)
    
    # Start the scheduler loop in a background daemon thread
    scheduler_thread = threading.Thread(target=scheduler.run_scheduler_loop, daemon=True)
    scheduler_thread.start()
    
    # Start the interactive CLI in the main thread
    interactive_cli(scheduler)
