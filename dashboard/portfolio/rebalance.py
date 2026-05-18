"""L4: Rebalance generator — diff current vs target, apply turnover budget."""
import logging
from datetime import datetime

import pandas as pd
import yaml
from pathlib import Path

from portfolio.state import get_positions
from portfolio.transaction_costs import estimate_cost_bps

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())


def generate_rebalance(
    target_weights: dict[str, float],
    aum: float,
    whatif: bool = False,
) -> list[dict]:
    """
    Compare current positions to target weights.
    Returns list of trade orders: {ticker, action, shares, est_cost_bps, reason}.
    Applies 30% turnover budget.
    """
    positions = get_positions()
    pos_dict = {}
    if not positions.empty:
        for _, row in positions.iterrows():
            ticker = row["ticker"]
            cur_price = row.get("current_price") or row.get("entry_price", 100)
            cur_shares = row.get("shares", 0)
            pos_dict[ticker] = {"shares": cur_shares, "price": cur_price}

    trades = []
    turnover = 0.0
    max_turnover = _cfg["portfolio"]["turnover_budget"] * aum

    # Determine current weights
    total_portfolio_value = sum(
        abs(v["shares"] * v["price"]) for v in pos_dict.values()
    ) or aum

    current_weights = {
        t: (v["shares"] * v["price"]) / total_portfolio_value
        for t, v in pos_dict.items()
    }

    # Score changes: largest |target - current| first
    all_tickers = set(list(target_weights.keys()) + list(current_weights.keys()))
    diffs = []
    for t in all_tickers:
        tgt = target_weights.get(t, 0.0)
        cur = current_weights.get(t, 0.0)
        diffs.append((abs(tgt - cur), t, tgt, cur))
    diffs.sort(reverse=True)

    for _, ticker, tgt_w, cur_w in diffs:
        delta_w = tgt_w - cur_w
        if abs(delta_w) < 0.001:
            continue  # negligible change

        # Get current price
        if ticker in pos_dict:
            price = pos_dict[ticker]["price"]
        else:
            from data.db import get_conn
            conn = get_conn()
            row = conn.execute(
                "SELECT close FROM daily_prices WHERE ticker=? ORDER BY date DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            conn.close()
            price = float(row[0]) if row else 100.0

        delta_usd = delta_w * aum
        delta_shares = int(delta_usd / price)
        if delta_shares == 0:
            continue

        trade_usd = abs(delta_shares * price)

        # Turnover budget
        if turnover + trade_usd > max_turnover:
            logger.info("Turnover budget reached — stopping rebalance")
            break
        turnover += trade_usd

        action = "BUY" if delta_shares > 0 else "SELL"
        if tgt_w < 0 and cur_w >= 0:
            action = "SHORT"
        elif tgt_w >= 0 and cur_w < 0:
            action = "COVER"

        cost_bps = estimate_cost_bps(ticker, trade_usd, aum)

        trades.append({
            "ticker": ticker,
            "action": action,
            "shares": abs(delta_shares),
            "target_weight": round(tgt_w, 4),
            "current_weight": round(cur_w, 4),
            "delta_usd": round(delta_usd, 2),
            "est_cost_bps": round(cost_bps, 1),
            "price": price,
        })

    if whatif:
        print("\nWHAT-IF REBALANCE (no changes committed)")
        print(f"  Total trades: {len(trades)}")
        print(f"  Estimated turnover: ${turnover:,.0f} ({turnover/aum*100:.1f}%)")
        total_cost = sum(t["est_cost_bps"] * abs(t["delta_usd"]) / 10_000 for t in trades)
        print(f"  Estimated transaction costs: ${total_cost:,.0f}")
        for t in trades:
            print(f"  {t['action']:6} {t['ticker']:6} {t['shares']:6} shares "
                  f"@ ~${t['price']:.2f} | cost {t['est_cost_bps']:.1f}bps")

    return trades


def rebalance_schedule_advisory(conn) -> list[str]:
    """Return advisory warnings about upcoming market events."""
    warnings = []
    from data.earnings_calendar import get_upcoming_earnings
    upcoming = get_upcoming_earnings(conn, days=2)
    if upcoming:
        tickers = [u["ticker"] for u in upcoming]
        warnings.append(f"EARNINGS in 2 days: {', '.join(tickers[:5])}")

    # FOMC dates 2026 (hardcoded per spec)
    fomc_2026 = [
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-16",
    ]
    from datetime import timedelta
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for d in fomc_2026:
        if today <= d <= (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d"):
            warnings.append(f"FOMC meeting within 5 days: {d}")
            break

    # Monthly options expiry (3rd Friday)
    import calendar
    now = datetime.utcnow()
    c = calendar.monthcalendar(now.year, now.month)
    fridays = [week[calendar.FRIDAY] for week in c if week[calendar.FRIDAY] != 0]
    third_friday = datetime(now.year, now.month, fridays[2])
    days_to_opex = (third_friday - now).days
    if 0 <= days_to_opex <= 3:
        warnings.append(f"Monthly options expiry in {days_to_opex} days: {third_friday.strftime('%Y-%m-%d')}")

    return warnings
