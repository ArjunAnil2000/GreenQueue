import multiprocessing
import time
import sys
import signal

def cpu_burner():
    """A tight loop that forces the CPU core to 100% utilization."""
    try:
        while True:
            # Arbitrary math to keep the ALU busy
            _ = 3.14159 * 2.71828
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    # Default to 2 cores if not specified
    num_cores = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    
    print(f"[STRESS TEST] Burning {num_cores} cores. Press Ctrl+C to stop.")
    
    # Spawn child processes to burn CPU
    workers = []
    for _ in range(num_cores):
        p = multiprocessing.Process(target=cpu_burner)
        p.start()
        workers.append(p)

    def shutdown(signum, frame):
        for w in workers:
            w.terminate()
            w.join()
        sys.exit(0)

    # Catch SIGTERM (from your scheduler) and SIGINT (Ctrl+C)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Keep the main parent process alive
    while True:
        time.sleep(1)
