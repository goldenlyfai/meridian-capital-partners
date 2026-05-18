#!/usr/bin/env python3
"""L6 Entry Point: Meridian Capital Partners — Execution."""
import argparse
import logging
import signal
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
logging.basicConfig(
    level=getattr(logging, cfg["logging"]["level"]),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_execution")
AUM = cfg["fund"]["aum_usd"]


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Execution")
    parser.add_argument("--dry-run", action="store_true", help="Log trades without placing orders")
    parser.add_argument("--execute", action="store_true", help="Place real orders on Alpaca")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        parser.print_help()
        sys.exit(0)

    from execution.executor import execute_trade, cancel_all_pending
    from portfolio.state import init_portfolio_tables, get_positions
    from portfolio.rebalance import generate_rebalance

    # Graceful shutdown
    def _sigint(sig, frame):
        logger.info("SIGINT — cancelling pending orders")
        cancel_all_pending()
        sys.exit(0)
    signal.signal(signal.SIGINT, _sigint)

    init_portfolio_tables()

    # Get rebalance trades
    scored_path = ROOT / "output" / "scored_universe_latest.csv"
    if not scored_path.exists():
        logger.error("Run run_scoring.py and run_portfolio.py first")
        sys.exit(1)

    import pandas as pd
    scored = pd.read_csv(scored_path, index_col="ticker")
    longs = scored[scored["signal"] == "LONG"].head(cfg["portfolio"]["num_longs"])
    shorts = scored[scored["signal"] == "SHORT"].tail(cfg["portfolio"]["num_shorts"])

    from portfolio.optimizer import conviction_optimize
    target_weights = conviction_optimize(longs, shorts, AUM, cfg["portfolio"])
    trades = generate_rebalance(target_weights, AUM)

    if not trades:
        logger.info("No trades needed")
        return

    logger.info("%d trades to execute", len(trades))

    # Build current context for pre-trade checks
    positions = get_positions()
    current_weights = {}
    current_sectors = {}
    if not positions.empty:
        for _, row in positions.iterrows():
            price = row.get("current_price") or row.get("entry_price", 100)
            current_weights[row["ticker"]] = row["shares"] * price / AUM
            current_sectors[row["ticker"]] = row.get("sector", "Unknown")

    results = []
    for trade in trades:
        ticker = trade["ticker"]
        action = trade["action"]
        shares = int(trade["shares"])
        sector = scored.loc[ticker, "sector"] if ticker in scored.index else "Unknown"

        result = execute_trade(
            ticker=ticker,
            action=action,
            shares=shares,
            dry_run=not args.execute,
            current_weights=current_weights,
            current_sectors=current_sectors,
            ticker_sector=sector,
        )
        results.append(result)
        logger.info("%-10s %-6s %-6s %-5d -> %s",
                    result.get("status"), action, ticker, shares,
                    result.get("fill_price", result.get("reason", "")))

    # Summary
    filled = [r for r in results if r["status"] == "FILLED"]
    rejected = [r for r in results if r["status"] == "REJECTED"]
    print(f"\nExecution complete: {len(filled)} filled, {len(rejected)} rejected")
    for r in rejected:
        print(f"  REJECTED {r['ticker']}: {r['reason']}")


if __name__ == "__main__":
    main()
