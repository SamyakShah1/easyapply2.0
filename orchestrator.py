"""
orchestrator.py — EasyApply Master Controller
Runs Naukri + Internshala agents in parallel as subprocesses,
streams their logs live to terminal with color-coded prefixes,
and launches the real-time dashboard automatically.

Usage:
    .venv\\Scripts\\python.exe orchestrator.py
"""
import subprocess
import threading
import sys
import os
import time
import webbrowser
import signal
from datetime import datetime

# Force UTF-8 on Windows terminal (prevents charmap crash from Unicode chars)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── ANSI colors ───────────────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[96m"     # Naukri
PURPLE  = "\033[95m"     # Internshala
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
DIM     = "\033[2m"

PYTHON = os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "python.exe")
BASE   = os.path.dirname(os.path.abspath(__file__))

processes: list[subprocess.Popen] = []

def ts():
    return datetime.now().strftime("%H:%M:%S")

def banner():
    print(f"""\n{BOLD}{PURPLE}
  +==================================================+
  |  [ROCKET] EasyApply Orchestrator                 |
  |  Naukri + Internshala  --  Parallel Run          |
  +==================================================+
{RESET}""")

def stream_logs(proc: subprocess.Popen, prefix: str, color: str):
    """Stream stdout of a subprocess to terminal with colored prefix."""
    for line in iter(proc.stdout.readline, b""):
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            print(f"{DIM}[{ts()}]{RESET} {color}{BOLD}[{prefix}]{RESET} {text}", flush=True)
    proc.stdout.close()

def start_agent(script: str, label: str, color: str) -> subprocess.Popen:
    """Launch an agent script as a subprocess and stream its logs."""
    script_path = os.path.join(BASE, script)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"          # prevent charmap crash on Windows
    env["PYTHONUTF8"] = "1"                    # Python 3.7+ UTF-8 mode
    proc = subprocess.Popen(
        [PYTHON, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=BASE,
        bufsize=1,
        env=env,
    )
    processes.append(proc)
    t = threading.Thread(target=stream_logs, args=(proc, label, color), daemon=True)
    t.start()
    print(f"{GREEN}✓ {label} agent started (PID {proc.pid}){RESET}", flush=True)
    return proc

def start_dashboard() -> subprocess.Popen:
    """Start the dashboard server subprocess."""
    script_path = os.path.join(BASE, "run_dashboard.py")
    proc = subprocess.Popen(
        [PYTHON, script_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=BASE,
    )
    processes.append(proc)
    return proc

def kill_all():
    print(f"\n{YELLOW}Shutting down all agents...{RESET}", flush=True)
    for proc in processes:
        try:
            proc.terminate()
        except Exception:
            pass
    time.sleep(1)
    for proc in processes:
        try:
            proc.kill()
        except Exception:
            pass
    print(f"{GREEN}All agents stopped. Goodbye!{RESET}", flush=True)

def main():
    banner()

    # ── Start dashboard ────────────────────────────────────────────────────────
    print(f"{BOLD}[1/3]{RESET} Starting dashboard server...")
    dash = start_dashboard()
    time.sleep(1.5)
    webbrowser.open("http://localhost:8765")
    print(f"{GREEN}✓ Dashboard open at http://localhost:8765{RESET}\n")

    # ── Start Naukri agent ─────────────────────────────────────────────────────
    print(f"{BOLD}[2/3]{RESET} Starting {CYAN}{BOLD}Naukri{RESET} agent...")
    naukri = start_agent("naukri_agent.py", "NAUKRI", CYAN)
    time.sleep(2)  # slight stagger so Chrome gets to initialize

    # ── Start Internshala agent ───────────────────────────────────────────────
    print(f"{BOLD}[3/3]{RESET} Starting {PURPLE}{BOLD}Internshala{RESET} agent...")
    internshala = start_agent("autopilot_agent.py", "INTERNSHALA", PURPLE)

    print(f"\n{DIM}{'─'*55}{RESET}")
    print(f"{BOLD}Both agents running. Press Ctrl+C to stop all.{RESET}")
    print(f"{DIM}{'─'*55}{RESET}\n")

    # ── Register Ctrl+C handler ────────────────────────────────────────────────
    def handle_interrupt(sig, frame):
        kill_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    # ── Wait for both agents to finish ────────────────────────────────────────
    naukri.wait()
    internshala.wait()

    print(f"\n{GREEN}{BOLD}Both agents finished.{RESET}")

    # Print summary from tracker
    try:
        sys.path.insert(0, BASE)
        import tracker
        stats = tracker.get_stats()
        print(f"""
{BOLD}{'='*45}
  📊  Run Summary
{'='*45}{RESET}
  Total applications logged : {BOLD}{stats['total']}{RESET}
  By status  : {stats['by_status']}
  By platform: {stats['by_platform']}
{BOLD}{'='*45}{RESET}
  Dashboard : http://localhost:8765
  CSV report: {os.path.join(BASE, 'applications.csv')}
""")
    except Exception:
        pass

    input(f"{DIM}Press Enter to also stop the dashboard server...{RESET}")
    kill_all()

if __name__ == "__main__":
    main()
