#!/usr/bin/env python3
"""L1 Entry Point: Meridian Capital Partners — Data Refresh."""
import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from paths import log_file as _log_file, output_dir as _output_dir  # noqa: E402
cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
log_path = _log_file()
log_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, cfg["logging"]["level"], logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_path),
    ],
)
logger = logging.getLogger("run_data")


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Data Layer")
    parser.add_argument("--no-filings", action="store_true", help="Skip SEC filings (faster daily run)")
    parser.add_argument("--no-13f", action="store_true", help="Skip 13-F institutional holdings")
    parser.add_argument("--ticker", help="Single ticker mode")
    parser.add_argument("--lookback-years", type=int, default=cfg["market_data"]["lookback_years"],
                        help="Price history lookback in years (default 3; use 1 for faster first run)")
    args = parser.parse_args()

    from data.db import init_db
    from data.universe import refresh_universe, get_sp500_tickers, get_all_tickers
    from data.market_data import refresh_prices
    from data.fundamentals import refresh_fundamentals
    from data.short_interest import refresh_short_interest
    from data.estimates import refresh_estimates
    from data.earnings_calendar import refresh_earnings_calendar
    from data.transcripts import refresh_transcripts
    from data.sec_data import refresh_sec_filings
    from data.institutional import refresh_institutional
    from data.db import get_conn

    logger.info("=" * 60)
    logger.info("MERIDIAN CAPITAL PARTNERS — Data Refresh")
    logger.info("=" * 60)

    # Init DB schema
    init_db()

    # 1. Universe
    logger.info("[1/8] Refreshing universe…")
    n_stocks = refresh_universe(refresh_days=cfg["universe"]["refresh_days"])

    conn = get_conn()
    if args.ticker:
        tickers = [args.ticker.upper()]
        all_tickers = tickers
    else:
        tickers = get_sp500_tickers(conn)
        all_tickers = get_all_tickers(conn)
    conn.close()
    logger.info("Universe: %d S&P 500 stocks", len(tickers))

    # 2. Market data
    logger.info("[2/8] Fetching daily prices…")
    price_summary = refresh_prices(
        all_tickers,
        lookback_years=args.lookback_years,
    )
    logger.info(
        "Prices: %d tickers updated, %d bars added, %d errors",
        price_summary["tickers_updated"],
        price_summary["bars_added"],
        len(price_summary["errors"]),
    )

    # 3. Fundamentals
    logger.info("[3/8] Fetching fundamentals…")
    fund_summary = refresh_fundamentals(tickers[:50] if not args.ticker else tickers)
    logger.info("Fundamentals: %d tickers updated", fund_summary["updated"])

    # 4. Short interest
    logger.info("[4/8] Fetching short interest…")
    si_summary = refresh_short_interest(tickers)
    logger.info("Short interest: %d updated", si_summary["updated"])

    # 5. Analyst estimates
    logger.info("[5/8] Fetching analyst estimates…")
    est_summary = refresh_estimates(tickers)
    logger.info("Estimates: %d updated", est_summary["updated"])

    # 6. Earnings calendar
    logger.info("[6/8] Fetching earnings calendar…")
    cal_summary = refresh_earnings_calendar(tickers)
    logger.info("Earnings calendar: %d tickers with dates", cal_summary["updated"])

    # 7. Transcripts (if FMP key available)
    logger.info("[7/8] Fetching earnings transcripts…")
    tr_summary = refresh_transcripts(tickers[:20] if not args.ticker else tickers)
    if tr_summary.get("skipped"):
        logger.info("Transcripts: skipped (%s)", tr_summary.get("reason", ""))
    else:
        logger.info("Transcripts: %d fetched", tr_summary.get("fetched", 0))

    # 8. SEC filings
    if not args.no_filings:
        logger.info("[8a/8] Fetching SEC Form 4 filings…")
        sec_summary = refresh_sec_filings(tickers[:30] if not args.ticker else tickers)
        logger.info(
            "SEC Form4: %d tickers done, %d insider transactions",
            sec_summary["tickers_done"],
            sec_summary["insider_txns"],
        )
    else:
        logger.info("[8a/8] SEC filings skipped (--no-filings)")

    if not args.no_13f:
        logger.info("[8b/8] Fetching 13-F institutional holdings…")
        inst_summary = refresh_institutional()
        logger.info(
            "13-F: %d funds, %d holdings",
            inst_summary.get("funds_done", 0),
            inst_summary.get("holdings", 0),
        )
    else:
        logger.info("[8b/8] 13-F holdings skipped (--no-13f)")

    logger.info("=" * 60)
    logger.info("DATA REFRESH COMPLETE")
    logger.info("  Universe:       %d stocks", len(tickers))
    logger.info("  Price bars:     %d added", price_summary["bars_added"])
    logger.info("  Fundamentals:   %d tickers", fund_summary["updated"])
    logger.info("  Short interest: %d tickers", si_summary["updated"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
