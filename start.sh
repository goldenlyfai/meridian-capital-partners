#!/bin/bash
# Meridian Capital Partners — Local launcher
# Starts FastAPI backend + Next.js dashboard, opens browser

set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and add your API keys."
  exit 1
fi

echo "Starting Meridian Capital Partners..."

# Start FastAPI backend on port 8000
echo "  [1/2] Starting Python backend (port 8000)..."
python3 api_server.py &
BACKEND_PID=$!

# Wait for backend to be ready
echo "  Waiting for backend..."
for i in {1..20}; do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "  Backend ready."
    break
  fi
  sleep 1
done

# Start Next.js dashboard on port 3000
echo "  [2/2] Starting Next.js dashboard (port 3000)..."
cd dashboard
npm run dev &
FRONTEND_PID=$!

# Open browser after a short delay
sleep 3
open http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null || true

echo ""
echo "  MERIDIAN CAPITAL PARTNERS — JARVIS"
echo "  Dashboard: http://localhost:3000"
echo "  API:       http://localhost:8000"
echo ""
echo "  Press Ctrl+C to stop."

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
