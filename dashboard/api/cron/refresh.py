"""
Vercel Cron Job — runs daily after market close (Mon-Fri 22:00 UTC).
Refreshes prices, short interest, estimates, earnings calendar, then re-scores.
Called automatically by Vercel; also callable manually from the dashboard.
"""
import sys
import os

# dashboard/ is the Vercel root — go up 2 levels: cron/ → api/ → dashboard/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from http.server import BaseHTTPRequestHandler
import json
import subprocess
import threading


def _run_refresh():
    subprocess.run(
        [sys.executable, "run_data.py", "--no-filings", "--no-13f"],
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "run_scoring.py"],
        capture_output=True,
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Verify this is a legitimate Vercel cron call
        auth = self.headers.get("Authorization", "")
        cron_secret = os.getenv("CRON_SECRET", "")
        if cron_secret and auth != f"Bearer {cron_secret}":
            self.send_response(401)
            self.end_headers()
            return

        # Fire and forget — Vercel cron has a 300s limit
        t = threading.Thread(target=_run_refresh, daemon=True)
        t.start()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "refresh started"}).encode())
