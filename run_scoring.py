#!/usr/bin/env python3
"""L2 Entry Point: Meridian Capital Partners — Scoring Engine."""
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

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
logger = logging.getLogger("run_scoring")


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Scoring")
    parser.add_argument("--ticker", help="Single ticker mode")
    parser.add_argument("--sector", help="Score only this GICS sector")
    args = parser.parse_args()

    from data.db import get_conn, init_db
    from data.universe import get_universe_df
    from factors.composite import compute_all_factors, compute_composite
    from factors.crowding import detect_crowding
    from factors.regime_weights import get_vix_level

    init_db()
    conn = get_conn()
    universe_df = get_universe_df(conn)
    universe_df = universe_df[universe_df["is_benchmark"] == 0].copy()
    conn.close()

    if args.ticker:
        universe_df = universe_df[universe_df["ticker"] == args.ticker.upper()]
        if universe_df.empty:
            logger.error("Ticker %s not in universe", args.ticker)
            sys.exit(1)

    if args.sector:
        universe_df = universe_df[universe_df["sector"] == args.sector]
        if universe_df.empty:
            logger.error("No tickers found for sector: %s", args.sector)
            sys.exit(1)

    logger.info("Scoring %d tickers…", len(universe_df))

    vix = get_vix_level()
    logger.info("VIX: %.1f", vix)

    factor_df = compute_all_factors(universe_df)
    scored = compute_composite(factor_df, universe_df, vix=vix)

    # Crowding detection
    crowding_alerts = detect_crowding(factor_df)

    # Save results
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    latest_path = output_dir / "scored_universe_latest.csv"
    archive_path = output_dir / f"scored_universe_{ts}.csv"
    scored.to_csv(latest_path)
    scored.to_csv(archive_path)
    logger.info("Scores saved: %s", latest_path)

    # Print summary
    longs = scored[scored["signal"] == "LONG"].head(5)
    shorts = scored[scored["signal"] == "SHORT"].tail(5)

    print("\n" + "=" * 70)
    print("MERIDIAN CAPITAL PARTNERS — SCORING SUMMARY")
    print("=" * 70)
    print(f"VIX: {vix:.1f} | Universe: {len(scored)} tickers")
    print(f"Long candidates: {(scored['signal']=='LONG').sum()} | "
          f"Short candidates: {(scored['signal']=='SHORT').sum()}")

    print("\nTOP 5 LONGS:")
    print(longs[["company_name", "sector", "composite", "momentum", "quality", "value"]].to_string())

    print("\nTOP 5 SHORTS:")
    print(shorts[["company_name", "sector", "composite", "momentum", "quality", "value"]].to_string())

    if crowding_alerts:
        print("\nCROWDING WARNINGS:")
        for alert in crowding_alerts:
            print(f"  [{alert['severity']}] {alert['factor_pair']}: "
                  f"corr={alert['actual_corr']:.2f} (baseline={alert['baseline_corr']:.2f})")
    else:
        print("\nNo crowding alerts.")

    # Degenerate factor warnings
    for col in factor_df.columns:
        s = factor_df[col]
        if (s.fillna(50) == 50).mean() > 0.90:
            logger.warning("DEGENERATE FACTOR: %s — >90%% of scores are 50 (neutral)", col)

    print("=" * 70)


if __name__ == "__main__":
    main()
