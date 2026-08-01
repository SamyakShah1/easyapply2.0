import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class AgentBridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/run-all":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Since Playwright can take some time, we just kick off the scripts sequentially
            # Note: For MVP we run them synchronously, so n8n waits for completion.
            print("[Bridge] Trigger received from n8n. Starting Scraper Agents...")
            
            scripts = [
                "naukri_scanner.py",
                "instahyre_scanner.py",
                "linkedin_scanner.py"
            ]
            
            # Using the venv python to ensure playwright works
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
        else:
            self.send_response(404)
            self.end_headers()

def run(server_class=HTTPServer, handler_class=AgentBridgeHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"[Bridge] Agent Server listening on port {port}...")
    print(f"Waiting for n8n triggers on http://localhost:{port}/run-all")
    httpd.serve_forever()

if __name__ == '__main__':
    run()
