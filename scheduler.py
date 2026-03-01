import os
import signal
import time
import subprocess
import psutil
from collections import deque

class Task:
    def __init__(self, name, cmd, initial_i=5.0):
        self.name = name
        self.cmd = cmd
        self.pid = None
        self.proc = None  # Holds the psutil.Process object
        self.i = initial_i
        self.is_running = False

    def start(self):
        if self.pid is None:
            # First time starting
            process = subprocess.Popen(self.cmd, shell=True)
            self.pid = process.pid
            self.proc = psutil.Process(self.pid)

            # Call cpu_percent() once with interval=None to initialize the internal timers
            self.proc.cpu_percent(interval=None)
        else:
            # Resuming from a paused state
            os.kill(self.pid, signal.SIGCONT)
            # Re-seed the timer so the pause duration isn't counted as 0% CPU time
            self.proc.cpu_percent(interval=None)

        self.is_running = True
        print(f"[START/RESUME] Task {self.name} (PID: {self.pid})")

    def pause(self):
        if self.pid and self.is_running:
            os.kill(self.pid, signal.SIGSTOP)
            self.is_running = False
            print(f"[PAUSE] Task {self.name} (PID: {self.pid}) stopped. I={self.i:.2f}")

class GEASScheduler:
    def __init__(self, k=1.0, alpha=0.2):
        self.k = k
        self.alpha = alpha  # EWMA_t = alpha * r_t + (1 - alpha) * EWMA_{t-1} 
        self.queue = deque()
        self.running_tasks = []
        self.current_gi = 10.0
        self.ti = 0.0
        self.num_cores = psutil.cpu_count(logical=True)

    def submit_task(self, task):
        print(f"[SUBMIT] New task added to queue: {task.name}")
        self.queue.append(task)

    def update_gi(self, new_gi):
        """Called hourly (or when your LSTM outputs a new prediction)"""
        print(f"\n[GI UPDATE] Greenness Index changed from {self.current_gi} to {new_gi}")
        self.current_gi = new_gi

    def measure_actual_intensiveness(self, task):
        """
        Measures the CPU utilization over the last minute and maps it to a 0-10 scale.
        """
        if not task.is_running or task.proc is None:
            return 0.0

        try:
            # 1. Get CPU percent since the last call (non-blocking)
            # Note: This can exceed 100% on multi-core systems (e.g., 400% on 4 cores)
            raw_cpu_percent = task.proc.cpu_percent(interval=None)
            
            # 2. Normalize to a system-wide percentage (0 to 100)
            system_wide_percent = raw_cpu_percent / self.num_cores
            
            # 3. Map 0-100% to your 0.0 - 10.0 scale
            # We divide by 10 because (percent / 100) * 10 is mathematically the same as percent / 10
            measured_i = system_wide_percent / 10.0
            
            # Cap it at 10.0 to prevent outlier spikes from breaking the math
            return min(max(measured_i, 0.0), 10.0)  # why the fxxk there is a max function?

        except psutil.NoSuchProcess:
            # Task finished or crashed
            eprint(f"\n[STATUS] Process {self.pid} finished or crashed.")
            return 0.0

    def tick_minute(self):
        """The per-minute control loop."""
        print(f"\n--- Minute Tick | GI: {self.current_gi} | Capacity: {self.k * self.current_gi:.2f} ---")
        
        # 1. Update I for all running tasks using EWMA
        self.ti = 0.0
        for task in self.running_tasks:
            actual_i = self.measure_actual_intensiveness(task)
            task.i = (1 - self.alpha) * task.i + (self.alpha * actual_i)
            print(f"[STATUS] Actual I of process {task.pid}: {actual_i:.2f}")
            print(f"[STATUS] EWMA I of process {task.pid}: {task.i:.2f}")
            self.ti += task.i

        print(f"[STATUS] Current TI: {self.ti:.2f}")

        # 2. Enforce the Ceiling (Stop heaviest tasks if TI is too high)
        capacity = self.k * self.current_gi
        
        while self.ti >= capacity and self.running_tasks:
            # Find the heaviest task
            heaviest_task = max(self.running_tasks, key=lambda t: t.i)
            
            # Preempt it
            heaviest_task.pause()
            self.running_tasks.remove(heaviest_task)
            self.queue.append(heaviest_task) # Put back in queue
            
            # Update TI
            self.ti -= heaviest_task.i
            print(f"[PREEMPT] Evicted {heaviest_task.name}. New TI: {self.ti:.2f}")

        # 3. Fill the Void (Admit tasks if we have spare green capacity)
        while self.queue:
            next_task = self.queue[0]
            
            # Check if adding this task keeps us under the limit
            if self.ti + next_task.i < capacity:
                self.queue.popleft() # Remove from queue
                next_task.start()
                self.running_tasks.append(next_task)
                self.ti += next_task.i
            else:
                # If the task at the front of the queue is too heavy, we stop admitting.
                # (You could also search the queue for a smaller task, but strict FIFO prevents starvation)
                break

    def run_scheduler_loop(self):
        """Main loop simulating the passage of time."""
        try:
            while True:
                self.tick_minute()
                time.sleep(60) # Wait for the next minute
        except KeyboardInterrupt:
            print("Shutting down scheduler... Aborting all tasks...")
            
            # Terminate all tasks in queue
            while self.queue:
                task = self.queue.popleft()

                # Stopped tasks
                if task.pid:
                    os.kill(task.pid, signal.SIGTERM)

            # Terminate all running tasks
            for t in self.running_tasks:
                os.kill(t.pid, signal.SIGTERM)

            print("All tasks have been terminated. Shutting down scheduler...")

# --- Example Usage ---
if __name__ == "__main__":
    scheduler = GEASScheduler(k=2.0, alpha=0.3)
    
    # Simulating task submission
    scheduler.submit_task(Task("AI_Train_1", "sleep 1000", initial_i=8.0))
    scheduler.submit_task(Task("Data_Prep", "sleep 1000", initial_i=4.0))
    scheduler.submit_task(Task("AI_Train_2", "sleep 1000", initial_i=6.0))

    # Simulate a scenario
    scheduler.update_gi(5.0) # Capacity = 10.0
    scheduler.tick_minute()  # Will start AI_Train_1. TI becomes 8. Data_Prep stays in queue.
    
    scheduler.update_gi(2.0) # Grid gets dirty. Capacity drops to 4.0.
    scheduler.tick_minute()  # AI_Train_1 (I=8) is preempted. Data_Prep (I=4) is admitted.
