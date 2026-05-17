#!/usr/bin/env python3
"""FastAPI bridge — serves Python backend data to the Next.js dashboard."""
import logging
import sys
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="Meridian Capital Partners API", version="1.0.0")

# In production (Railway) allow the Vercel frontend origin.
# ALLOWED_ORIGINS env var = comma-separated list, e.g. "https://meridian.vercel.app"
import os as _os
_extra_origins = [o.strip() for o in _os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"] + _extra_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    from data.db import get_conn
    try:
        conn = get_conn()
        n = conn.execute("SELECT COUNT(*) FROM universe").fetchone()[0]
        conn.close()
        return {"status": "ok", "universe_size": n}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

AUM = cfg["fund"]["aum_usd"]


# ─── PORTFOLIO ──────────────────────────────────────────────────────────────

@app.get("/api/portfolio/positions")
def get_positions():
    from portfolio.state import get_positions as _get, update_current_prices
    update_current_prices()
    df = _get()
    if df.empty:
        return {"positions": [], "summary": {}}
    pos = df.to_dict("records")
    long_pnl = sum(p["unrealized_pnl"] for p in pos if p.get("signal") == "LONG")
    short_pnl = sum(p["unrealized_pnl"] for p in pos if p.get("signal") == "SHORT")
    return {
        "positions": pos,
        "summary": {
            "total_positions": len(pos),
            "long_count": len([p for p in pos if p.get("signal") == "LONG"]),
            "short_count": len([p for p in pos if p.get("signal") == "SHORT"]),
            "total_unrealized_pnl": long_pnl + short_pnl,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
        },
    }


@app.get("/api/portfolio/beta")
def get_beta():
    from portfolio.state import get_positions as _get
    from portfolio.beta import compute_portfolio_beta
    df = _get()
    if df.empty:
        return {"long_beta": 0, "short_beta": 0, "net_beta": 0}
    weights = {}
    for _, row in df.iterrows():
        price = row.get("current_price") or row.get("entry_price", 100)
        weights[row["ticker"]] = row["shares"] * price / AUM
    lb, sb, nb = compute_portfolio_beta(weights)
    return {"long_beta": lb, "short_beta": sb, "net_beta": nb}


# ─── RESEARCH / SCORING ─────────────────────────────────────────────────────

@app.get("/api/research/candidates")
def get_candidates(limit: int = 20):
    import pandas as pd
    scored_path = ROOT / "output" / "scored_universe_latest.csv"
    if not scored_path.exists():
        raise HTTPException(404, "No scored universe. Run run_scoring.py first.")
    scored = pd.read_csv(scored_path, index_col="ticker")
    longs = scored[scored["signal"] == "LONG"].head(limit).reset_index().to_dict("records")
    shorts = scored[scored["signal"] == "SHORT"].tail(limit).reset_index().to_dict("records")
    return {"longs": longs, "shorts": shorts}


@app.get("/api/research/crowding")
def get_crowding():
    import pandas as pd
    scored_path = ROOT / "output" / "scored_universe_latest.csv"
    if not scored_path.exists():
        return {"alerts": []}
    scored = pd.read_csv(scored_path, index_col="ticker")
    from factors.crowding import detect_crowding
    alerts = detect_crowding(scored)
    return {"alerts": alerts}


@app.get("/api/research/vix")
def get_vix():
    from factors.regime_weights import get_vix_level, get_weights
    vix = get_vix_level()
    weights = get_weights(vix=vix)
    regime = "low_vol" if vix < 15 else ("high_vol" if vix > 25 else "normal")
    return {"vix": vix, "regime": regime, "weights": weights}


@app.get("/api/research/analysis/{ticker}")
def get_ticker_analysis(ticker: str):
    from analysis.combined_score import get_all_ai_results
    return get_all_ai_results(ticker.upper())


class JarvisChat(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/jarvis/chat")
def jarvis_chat(req: JarvisChat):
    from reporting.jarvis import jarvis_chat as _chat
    response = _chat(req.message, req.history)
    return {"response": response}


# ─── RISK ────────────────────────────────────────────────────────────────────

@app.get("/api/risk/state")
def get_risk_state():
    from risk.risk_state import load
    return load()


@app.get("/api/risk/stress-tests")
def get_stress_tests():
    from portfolio.state import get_positions as _get
    df = _get()
    if df.empty:
        return {"results": []}
    weights = {}
    for _, row in df.iterrows():
        price = row.get("current_price") or row.get("entry_price", 100)
        weights[row["ticker"]] = row["shares"] * price / AUM
    from risk.stress_test import run_stress_tests
    results = run_stress_tests(weights, AUM)
    return {"results": results}


@app.get("/api/risk/pre-trade/{ticker}")
def pre_trade_check(ticker: str, action: str = "BUY", shares: int = 100):
    from portfolio.state import get_positions as _get
    df = _get()
    weights = {}
    sectors = {}
    for _, row in df.iterrows():
        price = row.get("current_price") or row.get("entry_price", 100)
        weights[row["ticker"]] = row["shares"] * price / AUM
        sectors[row["ticker"]] = row.get("sector", "Unknown")

    from data.db import get_conn
    conn = get_conn()
    sector_row = conn.execute("SELECT sector FROM universe WHERE ticker=?", (ticker.upper(),)).fetchone()
    conn.close()
    ticker_sector = sector_row[0] if sector_row else "Unknown"

    from data.market_data import get_prices
    conn2 = get_conn()
    prices = get_prices(conn2, ticker.upper(), days=5)
    conn2.close()
    price = float(prices["close"].iloc[-1]) if not prices.empty else 100.0

    from risk.pre_trade import pre_trade_check as _check
    approved, reason = _check(ticker.upper(), action, shares, price, AUM, weights, sectors, ticker_sector)
    return {"approved": approved, "reason": reason}


# ─── PERFORMANCE ─────────────────────────────────────────────────────────────

@app.get("/api/performance/attribution")
def get_attribution(days: int = 90):
    from reporting.pnl_attribution import get_attribution_history
    df = get_attribution_history(days=days)
    return {"data": df.to_dict("records") if not df.empty else []}


@app.get("/api/performance/equity-curve")
def get_equity_curve():
    from reporting.pnl_attribution import get_attribution_history
    from data.db import get_conn
    from data.market_data import get_prices
    import pandas as pd

    attr = get_attribution_history(days=252)
    if attr.empty:
        return {"fund": [], "spy": []}

    conn = get_conn()
    spy = get_prices(conn, "SPY", days=260)
    conn.close()

    fund_curve = (1 + attr["portfolio_return"]).cumprod()
    spy_curve = (1 + spy["adj_close"].pct_change()).cumprod() if not spy.empty else pd.Series()

    return {
        "fund": [{"date": d, "value": v * 100} for d, v in zip(attr["date"], fund_curve)],
        "spy": [{"date": str(i)[:10], "value": v * 100} for i, v in spy_curve.items()],
    }


# ─── EXECUTION ───────────────────────────────────────────────────────────────

@app.get("/api/execution/slippage")
def get_slippage(days: int = 30):
    from execution.costs import get_slippage_stats
    return get_slippage_stats(days=days)


@app.get("/api/execution/account")
def get_account():
    from execution.broker import get_account as _get
    return _get()


@app.post("/api/execution/approve/{ticker}")
def approve_trade(ticker: str, action: str = "BUY"):
    from data.db import get_conn
    from datetime import datetime
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO position_approvals
           (ticker, action, status, reviewed_at, reviewer) VALUES (?,?,?,?,?)""",
        (ticker.upper(), action, "APPROVED", datetime.utcnow().isoformat(), "dashboard"),
    )
    conn.commit()
    conn.close()
    return {"status": "approved", "ticker": ticker, "action": action}


# ─── LETTER / REPORTING ──────────────────────────────────────────────────────

@app.get("/api/letter/daily")
def get_daily_letter(refresh: bool = False):
    from reporting.jarvis import generate_lp_letter
    letter = generate_lp_letter(force_refresh=refresh)
    return {"letter": letter}


@app.get("/api/letter/weekly-commentary")
def get_weekly_commentary():
    from reporting.jarvis import generate_weekly_commentary
    text = generate_weekly_commentary()
    return {"commentary": text}


# ─── UNIVERSE ────────────────────────────────────────────────────────────────

@app.get("/api/universe/stats")
def get_universe_stats():
    from data.db import get_conn
    from data.earnings_calendar import get_upcoming_earnings
    from data.sec_data import detect_cluster_buying
    conn = get_conn()
    n_universe = conn.execute("SELECT COUNT(*) FROM universe WHERE is_benchmark=0").fetchone()[0]
    upcoming = get_upcoming_earnings(conn, days=7)
    ceo_buys = conn.execute(
        """SELECT COUNT(*) FROM insider_transactions
           WHERE is_ceo_cfo=1 AND transaction_code='P'
           AND date >= date('now', '-30 days')"""
    ).fetchone()[0]
    cluster_count = 0
    tickers = [r[0] for r in conn.execute("SELECT ticker FROM universe WHERE is_benchmark=0 LIMIT 50").fetchall()]
    for t in tickers:
        if detect_cluster_buying(conn, t):
            cluster_count += 1
    conn.close()
    return {
        "universe_size": n_universe,
        "earnings_next_7d": len(upcoming),
        "ceo_buys_30d": ceo_buys,
        "cluster_buys": cluster_count,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
