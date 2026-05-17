# Meridian Capital Partners — JARVIS System

A 7-layer long/short equity hedge fund system powered by Claude AI.

## Architecture

```
L1  data/           Data ingestion — 9 sources, SQLite
L2  factors/        Scoring engine — 8 factors, 27 sub-factors
L3  analysis/       Claude AI analyst — earnings, filings, risk, insiders
L4  portfolio/      Portfolio construction — MVO + conviction-tilt
L5  risk/           Risk management — pre-trade veto, circuit breakers
L6  execution/      Alpaca paper trading execution
L7  dashboard/      Next.js dashboard (JARVIS UI)
    reporting/      P&L attribution, LP letters, weekly commentary
    api_server.py   FastAPI bridge (Python ↔ Next.js)
```

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY at minimum
```

### 3. Run the pipeline (first time — full refresh)
```bash
# Layer 1: Fetch all data (~20-40 min first run)
python run_data.py

# Layer 2: Score the universe (~5 min)
python run_scoring.py

# Layer 3: Claude AI analysis on top candidates (~$2-5)
python run_analysis.py --estimate-cost   # preview cost
python run_analysis.py                    # run analysis

# Layer 4: Build target portfolio
python run_portfolio.py --whatif         # preview rebalance
python run_portfolio.py --rebalance      # commit rebalance

# Layer 5: Risk check
python run_risk_check.py --stress        # full risk check + stress tests

# Layer 6: Execute trades (paper trading)
python run_execution.py --dry-run        # preview
python run_execution.py --execute        # place orders
```

### 4. Start the dashboard
```bash
# Terminal 1: FastAPI backend
python api_server.py

# Terminal 2: Next.js frontend
cd dashboard && npm run dev
# Open http://localhost:3000
```

## Daily Automation (macOS)
```bash
cp com.user.hedgefund.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.hedgefund.daily.plist
```
Runs `run_scoring.py --no-filings --no-13f` weekdays at 17:15 (~10 min).

## Fast Daily Run (no SEC/13-F)
```bash
python run_data.py --no-filings --no-13f
python run_scoring.py
```

## Configuration
All parameters in `config.yaml`. Key settings:
- `portfolio.num_longs/num_shorts` — 20/20 default
- `portfolio.optimize_method` — `conviction` or `mvo`
- `analysis.model` — Claude model for AI analysis
- `risk.circuit_breakers.*` — loss thresholds
- `fund.aum_usd` — AUM for position sizing

## Optional API Keys (`.env`)
| Key | Unlocks |
|-----|---------|
| `POLYGON_API_KEY` | Licensed exchange price data |
| `FMP_API_KEY` | Earnings transcripts + structured financials |
| `FRED_API_KEY` | Real credit spread data (BAMLH0A0HYM2) |
| `ALPACA_API_KEY/SECRET` | Paper/live trade execution |

## Dashboard Pages
| Page | Description |
|------|-------------|
| I PORTFOLIO | JARVIS identity, positions, AI chat |
| II RESEARCH | Factor heatmap, L/S candidates, approve trades |
| III RISK | Circuit breakers, stress tests, MCTR, alerts |
| IV PERFORMANCE | Equity curve, attribution, sector alpha |
| V EXECUTION | Slippage stats, order history, Alpaca account |
| VI LETTER | Formal daily LP letter with JARVIS commentary |
