"""
run_dashboard.py — Local server for the job application dashboard.
Serves dashboard.html + JSON API endpoints.
Run: .venv\\Scripts\\python.exe run_dashboard.py
"""
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from datetime import datetime

# Force UTF-8 on Windows terminal (prevents charmap crash from Unicode chars)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
import tracker

PORT = 8765
DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

def tail_log(filename: str, n: int = 60) -> list[str]:
    """Return last n lines from a log file, or empty list if not found."""
    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception:
        return []

def agent_status(filename: str) -> str:
    """Infer agent status from log file modification time."""
    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
        return "idle"
    age = (datetime.now().timestamp() - os.path.getmtime(path))
    if age < 30:
        return "running"
    elif age < 300:
        return "recent"
    return "idle"

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence noisy server logs

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/applications":
            self.send_json(tracker.get_all())

        elif path == "/api/stats":
            self.send_json(tracker.get_stats())

        elif path == "/api/logs":
            self.send_json({
                "naukri": tail_log("naukri.log"),
                "internshala": tail_log("internshala.log"),
            })

        elif path == "/api/agent_status":
            self.send_json({
                "naukri":      agent_status("naukri.log"),
                "internshala": agent_status("internshala.log"),
            })

        elif path in ("/", "/dashboard"):
            with open(DASHBOARD_PATH, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/update_status":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            tracker.update_status(body["job_url"], body["status"])
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), DashboardHandler)
    url = f"http://localhost:{PORT}"
    print(f"\n{'='*55}")
    print(f"  📊 Job Application Dashboard: {url}")
    print(f"  Press Ctrl+C to stop.")
    print(f"{'='*55}\n", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard server stopped.")
