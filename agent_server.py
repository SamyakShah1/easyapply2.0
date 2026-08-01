import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import sqlite3

DB_PATH = "job_hunter.db"

class AgentBridgeHandler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if self.path == "/run-all":
            print("[Bridge] Trigger received from n8n. Starting Scraper Agents...")
            scripts = ["naukri_scanner.py", "instahyre_scanner.py", "linkedin_scanner.py"]
            
            python_exec = os.path.join(".venv", "Scripts", "python.exe")
            if not os.path.exists(python_exec):
                python_exec = "python"
                
            results = {}
            for script in scripts:
                print(f"[Bridge] Running {script}...")
                try:
                    subprocess.run([python_exec, script], check=True)
                    results[script] = "success"
                except subprocess.CalledProcessError as e:
                    print(f"[Bridge] Error running {script}: {e}")
                    results[script] = "failed"
            
            response = json.dumps({"status": "completed", "results": results})
            self.wfile.write(response.encode('utf-8'))
            
        elif self.path == "/get-new-jobs":
            print("[Bridge] n8n requested new jobs...")
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT title, company, job_url, salary, match_reason FROM scraped_jobs WHERE status = 'new'")
            rows = cursor.fetchall()
            conn.close()
            
            jobs = [dict(row) for row in rows]
            response = json.dumps({"jobs": jobs})
            self.wfile.write(response.encode('utf-8'))
            
        elif self.path == "/mark-notified":
            print("[Bridge] n8n marked jobs as notified...")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE scraped_jobs SET status = 'notified' WHERE status = 'new'")
            conn.commit()
            conn.close()
            
            response = json.dumps({"status": "success"})
            self.wfile.write(response.encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

def run(server_class=HTTPServer, handler_class=AgentBridgeHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"[Bridge] Agent Server listening on port {port}...")
    print(f"Available Endpoints for n8n:")
    print(f" - GET http://localhost:{port}/run-all")
    print(f" - GET http://localhost:{port}/get-new-jobs")
    print(f" - GET http://localhost:{port}/mark-notified")
    httpd.serve_forever()

if __name__ == '__main__':
    run()
