#!/usr/bin/env python3
"""L3 Entry Point: Meridian Capital Partners — Claude AI Analysis."""
import argparse
import logging
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
logger = logging.getLogger("run_analysis")


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — AI Analysis")
    parser.add_argument("--estimate-cost", action="store_true", help="Estimate cost without running")
    parser.add_argument("--ticker", help="Analyze single ticker")
    parser.add_argument("--sector", help="Analyze all candidates in sector")
    args = parser.parse_args()

    from analysis.cost_tracker import get_tracker, reset_tracker
    from analysis.cache import evict_expired

    evict_expired()
    reset_tracker()

    if args.estimate_cost:
        print("Estimated cost for full run (20 long + 20 short candidates): $2-5")
        print("  Earnings analyzer: ~$0.05/ticker (requires FMP transcript)")
        print("  Filing analyzer:   ~$0.03/ticker")
        print("  Risk analyzer:     ~$0.04/ticker (requires 10-K cached)")
        print("  Insider analyzer:  ~$0.02/ticker")
        print("  Caching means repeat runs are near-free")
        return

    scored_path = ROOT / "output" / "scored_universe_latest.csv"
    if not scored_path.exists():
        logger.error("Run run_scoring.py first to generate scored_universe_latest.csv")
        sys.exit(1)

    import pandas as pd
    scored_df = pd.read_csv(scored_path, index_col="ticker")

    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.sector:
        tickers = scored_df[scored_df["sector"] == args.sector].index.tolist()
    else:
        # Default: top 20 longs + top 20 shorts
        longs = scored_df[scored_df["signal"] == "LONG"].head(20).index.tolist()
        shorts = scored_df[scored_df["signal"] == "SHORT"].tail(20).index.tolist()
        tickers = longs + shorts

    logger.info("Running Claude AI analysis on %d tickers…", len(tickers))

    from analysis.combined_score import compute_combined_scores
    from analysis.report_generator import save_reports

    combined = compute_combined_scores(scored_df, tickers=tickers)

    output_dir = save_reports(combined)

    tracker = get_tracker()
    summary = tracker.summary()
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print(f"  Tickers analyzed: {len(tickers)}")
    print(f"  API calls:        {summary['calls']}")
    print(f"  Input tokens:     {summary['input_tokens']:,}")
    print(f"  Output tokens:    {summary['output_tokens']:,}")
    print(f"  Cache reads:      {summary['cache_read_tokens']:,}")
    print(f"  Total cost:       ${summary['total_cost_usd']:.3f}")
    print(f"  Reports saved to: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
