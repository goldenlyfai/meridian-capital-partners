"""L6: Alpaca broker connection — paper trading by default."""
import logging
import os
import time
from functools import lru_cache

import yaml
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"


def get_trading_client():
    from alpaca.trading.client import TradingClient
    mode = _cfg["execution"]["mode"]
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not secret:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")

    if mode == "live":
        confirm = input("Type 'YES I UNDERSTAND THE RISKS' to enable live trading: ")
        if confirm != "YES I UNDERSTAND THE RISKS":
            raise RuntimeError("Live trading not confirmed")
        paper = False
        logger.warning("LIVE TRADING MODE ACTIVE")
    else:
        paper = True
        logger.info("Paper trading mode (safe)")

    return TradingClient(api_key, secret, paper=paper)


def get_data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    return StockHistoricalDataClient(api_key, secret)


def sync_positions_from_alpaca(conn):
    """Pull current Alpaca positions into local DB."""
    try:
        client = get_trading_client()
        alpaca_positions = client.get_all_positions()
        from portfolio.state import upsert_position
        for pos in alpaca_positions:
            ticker = pos.symbol
            shares = float(pos.qty)
            if pos.side.value == "short":
                shares = -shares
            price = float(pos.avg_entry_price)
            upsert_position(
                ticker=ticker,
                shares=shares,
                price=price,
                sector="Unknown",
                signal="LONG" if shares > 0 else "SHORT",
                composite_score=50.0,
            )
        logger.info("Synced %d positions from Alpaca", len(alpaca_positions))
    except Exception as e:
        logger.warning("Alpaca sync failed: %s", e)


def get_account() -> dict:
    try:
        client = get_trading_client()
        acct = client.get_account()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
            "status": acct.status.value,
        }
    except Exception as e:
        logger.warning("get_account: %s", e)
        return {}
