#!/bin/sh
# Meridian Capital Partners — Docker startup script
# Runs on every Railway deploy. Auto-fetches data on first boot.

set -e

echo "=== Meridian Capital Partners — Starting ==="

# Ensure data directories exist on the mounted volume
mkdir -p /data/output /data/cache /data/output/reports /data/cache/sec_filings

# Init DB schema (idempotent — safe to run every time)
echo "[1/3] Initialising database schema..."
python -c "from data.db import init_db; init_db()"
echo "      DB ready."

# Check if universe has been populated yet (first-boot detection)
UNIVERSE_COUNT=$(python -c "
from data.db import get_conn
conn = get_conn()
n = conn.execute('SELECT COUNT(*) FROM universe').fetchone()[0]
conn.close()
print(n)
" 2>/dev/null || echo "0")

if [ "$UNIVERSE_COUNT" -eq "0" ]; then
    echo "[2/3] First boot detected — fetching S&P 500 data..."
    echo "      This takes ~20 minutes. The API starts immediately and"
    echo "      data populates in the background."
    # Run in background so the API is available immediately
    python run_data.py --no-filings --no-13f >> /data/output/startup.log 2>&1 &
    python run_scoring.py >> /data/output/startup.log 2>&1 &
    echo "      Data pipeline running in background (see /data/output/startup.log)"
else
    echo "[2/3] Database has $UNIVERSE_COUNT tickers — skipping initial fetch."
fi

# Start the FastAPI server
echo "[3/3] Starting API server on port ${PORT:-8000}..."
exec uvicorn api_server:app --host 0.0.0.0 --port "${PORT:-8000}"
