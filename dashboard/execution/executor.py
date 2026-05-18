"""L6: Order executor with pre-trade veto, limit orders, slippage tracking."""
import logging
import signal
import time
from datetime import datetime

import yaml
from pathlib import Path

from execution.broker import get_trading_client
from execution.short_check import check_shortable
from execution.costs import record_fill

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
ecfg = _cfg["execution"]
AUM = _cfg["fund"]["aum_usd"]

_pending_orders: dict[str, str] = {}  # order_id -> ticker


def _get_latest_price(ticker: str) -> float:
    from data.db import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT close FROM daily_prices WHERE ticker=? ORDER BY date DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    conn.close()
    return float(row[0]) if row else 100.0


def execute_trade(
    ticker: str,
    action: str,
    shares: int,
    dry_run: bool = False,
    current_weights: dict | None = None,
    current_sectors: dict | None = None,
    ticker_sector: str = "Unknown",
) -> dict:
    """
    Execute a single trade through Alpaca.
    Returns result dict with status, fill price, slippage.
    """
    current_weights = current_weights or {}
    current_sectors = current_sectors or {}

    # a) Pre-trade veto
    signal_price = _get_latest_price(ticker)
    from risk.pre_trade import pre_trade_check
    approved, reason = pre_trade_check(
        ticker, action, shares, signal_price, AUM,
        current_weights, current_sectors, ticker_sector,
    )
    if not approved:
        return {"status": "REJECTED", "reason": reason, "ticker": ticker}

    # b) Short availability check
    if action in ("SHORT", "SELL_SHORT"):
        if not check_shortable(ticker):
            return {"status": "REJECTED", "reason": "not shortable/ETB", "ticker": ticker}

    # c) Limit price: close * (1 ± 0.001)
    offset = ecfg["limit_slippage_bps"] / 10_000
    if action in ("BUY", "LONG"):
        limit_price = round(signal_price * (1 + offset), 2)
        side = "buy"
    else:
        limit_price = round(signal_price * (1 - offset), 2)
        side = "sell"

    # d) Chunk if > 2% ADV
    from data.db import get_conn
    from data.market_data import get_adv
    conn = get_conn()
    adv = get_adv(conn, ticker, window=20)
    conn.close()

    chunk_usd = adv * ecfg.get("chunk_adv_threshold", 0.02)
    trade_usd = shares * signal_price
    chunks = max(1, int(trade_usd / chunk_usd)) if chunk_usd > 0 else 1
    chunk_shares = max(1, shares // chunks)

    if dry_run:
        logger.info("DRY RUN: %s %s %d @ $%.2f (limit), %d chunks",
                    action, ticker, shares, limit_price, chunks)
        return {
            "status": "DRY_RUN",
            "ticker": ticker,
            "action": action,
            "shares": shares,
            "limit_price": limit_price,
            "signal_price": signal_price,
            "chunks": chunks,
        }

    # e) Submit limit order via Alpaca
    try:
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderType

        client = get_trading_client()
        filled_shares = 0
        filled_price = 0.0
        order_ids = []

        for _ in range(chunks):
            order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
            order_req = LimitOrderRequest(
                symbol=ticker,
                qty=chunk_shares,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
            )
            order = client.submit_order(order_req)
            order_ids.append(order.id)
            _pending_orders[order.id] = ticker

            # f) Poll every 5s for fill, 120s timeout, 3 retries
            filled = _wait_for_fill(client, order.id, timeout=ecfg["order_timeout_seconds"])
            if filled:
                filled_shares += filled["qty"]
                filled_price = filled["fill_price"]
                del _pending_orders[order.id]
            else:
                # Cancel and retry
                client.cancel_order_by_id(order.id)
                _pending_orders.pop(order.id, None)

        if filled_shares > 0:
            # g) Record slippage
            record_fill(ticker, action, filled_shares, signal_price, filled_price, order_ids[0])
            return {
                "status": "FILLED",
                "ticker": ticker,
                "action": action,
                "shares": filled_shares,
                "fill_price": filled_price,
                "signal_price": signal_price,
                "slippage_bps": (filled_price - signal_price) / signal_price * 10_000,
            }
        else:
            return {"status": "CANCELLED", "ticker": ticker, "reason": "timeout on all chunks"}

    except Exception as e:
        logger.error("Order execution %s: %s", ticker, e)
        return {"status": "ERROR", "ticker": ticker, "reason": str(e)}


def _wait_for_fill(client, order_id: str, timeout: int = 120) -> dict | None:
    elapsed = 0
    while elapsed < timeout:
        try:
            order = client.get_order_by_id(order_id)
            if order.status.value in ("filled", "partially_filled"):
                filled_qty = float(order.filled_qty or 0)
                fill_price = float(order.filled_avg_price or 0)
                return {"qty": filled_qty, "fill_price": fill_price}
        except Exception:
            pass
        time.sleep(ecfg["poll_interval_seconds"])
        elapsed += ecfg["poll_interval_seconds"]
    return None


def cancel_all_pending():
    """SIGINT handler — cancel all pending orders."""
    try:
        if not _pending_orders:
            return
        client = get_trading_client()
        for oid in list(_pending_orders.keys()):
            try:
                client.cancel_order_by_id(oid)
                logger.info("Cancelled pending order %s", oid)
            except Exception:
                pass
        _pending_orders.clear()
    except Exception as e:
        logger.error("cancel_all_pending: %s", e)
