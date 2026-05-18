#!/usr/bin/env python3
"""L4 Entry Point: Meridian Capital Partners — Portfolio Construction."""
import argparse
import logging
import sys
from pathlib import Path

import yaml
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
logging.basicConfig(
    level=getattr(logging, cfg["logging"]["level"]),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_portfolio")
pcfg = cfg["portfolio"]
AUM = cfg["fund"]["aum_usd"]


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Portfolio")
    parser.add_argument("--rebalance", action="store_true")
    parser.add_argument("--whatif", action="store_true", help="Show proposed changes without committing")
    parser.add_argument("--current", action="store_true", help="Show current portfolio")
    parser.add_argument("--optimize-method", choices=["mvo", "conviction"], default=pcfg["optimize_method"])
    args = parser.parse_args()

    from portfolio.state import init_portfolio_tables, get_positions, update_current_prices
    from portfolio.beta import compute_portfolio_beta

    init_portfolio_tables()
    update_current_prices()

    if args.current:
        positions = get_positions()
        if positions.empty:
            print("No current positions.")
            return
        print("\nCURRENT PORTFOLIO:")
        print(positions[["ticker", "shares", "entry_price", "current_price",
                          "unrealized_pnl", "sector", "signal"]].to_string(index=False))
        weights = {}
        for _, row in positions.iterrows():
            price = row["current_price"] or row["entry_price"]
            weights[row["ticker"]] = row["shares"] * price / AUM
        lb, sb, nb = compute_portfolio_beta(weights)
        print(f"\nPortfolio betas — Long: {lb:.2f} | Short: {sb:.2f} | Net: {nb:.2f}")
        return

    # Load scored universe
    scored_path = ROOT / "output" / "scored_universe_latest.csv"
    if not scored_path.exists():
        logger.error("Run run_scoring.py first")
        sys.exit(1)

    scored = pd.read_csv(scored_path, index_col="ticker")
    longs = scored[scored["signal"] == "LONG"].head(pcfg["num_longs"])
    shorts = scored[scored["signal"] == "SHORT"].tail(pcfg["num_shorts"])
    logger.info("Candidates: %d longs, %d shorts", len(longs), len(shorts))

    # Choose optimizer
    if args.optimize_method == "mvo":
        from portfolio.mvo_optimizer import mvo_optimize
        weights = mvo_optimize(longs, shorts, AUM, pcfg)
        if not weights:
            logger.warning("MVO failed — falling back to conviction")
            from portfolio.optimizer import conviction_optimize
            weights = conviction_optimize(longs, shorts, AUM, pcfg)
    else:
        from portfolio.optimizer import conviction_optimize
        weights = conviction_optimize(longs, shorts, AUM, pcfg)

    logger.info("Target portfolio: %d positions", len(weights))

    if args.rebalance or args.whatif:
        from portfolio.rebalance import generate_rebalance, rebalance_schedule_advisory
        from data.db import get_conn
        conn = get_conn()
        advisories = rebalance_schedule_advisory(conn)
        conn.close()

        if advisories:
            print("\nREBALANCE ADVISORY WARNINGS:")
            for w in advisories:
                print(f"  ⚠ {w}")

        trades = generate_rebalance(weights, AUM, whatif=args.whatif)

        if not args.whatif:
            print(f"\nREBALANCE PLAN: {len(trades)} trades")
            for t in trades:
                print(f"  {t['action']:6} {t['ticker']:6} {t['shares']:6} shares "
                      f"(${abs(t['delta_usd']):,.0f}, {t['est_cost_bps']:.1f}bps)")
            print(f"\nPass trades to run_execution.py to execute.")

    # Show summary
    long_w = sum(w for w in weights.values() if w > 0)
    short_w = sum(w for w in weights.values() if w < 0)
    net_w = long_w + short_w
    lb, sb, nb = compute_portfolio_beta(weights)

    print("\nPORTFOLIO SUMMARY:")
    print(f"  Long gross:  {long_w*100:.1f}%")
    print(f"  Short gross: {abs(short_w)*100:.1f}%")
    print(f"  Net:         {net_w*100:.1f}%")
    print(f"  Total gross: {(long_w + abs(short_w))*100:.1f}%")
    print(f"  Net beta:    {nb:.2f}")


if __name__ == "__main__":
    main()
