"""L5: Pre-trade veto — 8 checks with ABSOLUTE VETO POWER."""
import logging
from datetime import datetime

import yaml
from pathlib import Path

from data.db import get_conn
from data.market_data import get_adv
from data.earnings_calendar import has_earnings_soon
from portfolio.state import get_positions
from portfolio.beta import compute_beta

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
rcfg = _cfg["risk"]["pre_trade_limits"]
pcfg = _cfg["portfolio"]
HALT_FILE = ROOT / "cache" / "HALT.lock"


def _log_rejection(ticker: str, reason: str, trade: dict):
    logger.warning("VETO: %s — %s | %s", ticker, reason, trade)
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS veto_log
           (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, reason TEXT,
            trade_json TEXT, vetoed_at TEXT)""",
    )
    import json
    conn.execute(
        "INSERT INTO veto_log (ticker, reason, trade_json, vetoed_at) VALUES (?,?,?,?)",
        (ticker, reason, json.dumps(trade), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def pre_trade_check(
    ticker: str,
    action: str,
    shares: float,
    price: float,
    aum: float,
    current_weights: dict[str, float],
    current_sectors: dict[str, str],
    ticker_sector: str,
) -> tuple[bool, str]:
    """
    Returns (approved: bool, reason: str).
    Closing/covering trades always approved.
    """
    trade = {"ticker": ticker, "action": action, "shares": shares, "price": price}

    # Closing trades bypass veto
    if action in ("CLOSE", "COVER", "SELL_CLOSE"):
        return True, "closing trade approved"

    # 1. Halt lock
    if HALT_FILE.exists():
        reason = "KILL_SWITCH halt lock active — no new trades"
        _log_rejection(ticker, reason, trade)
        return False, reason

    # 2. Earnings blackout (reduce only, don't block)
    conn = get_conn()
    if has_earnings_soon(conn, ticker, days=rcfg["earnings_blackout_days"]):
        if shares > 0:
            # Apply size cut — caller must respect this
            pass  # logged but not rejected; executor halves size
        logger.info("Earnings blackout for %s — size cut applies", ticker)

    # 3. Liquidity: <= 5% ADV
    adv = get_adv(conn, ticker, window=20)
    conn.close()
    trade_usd = abs(shares * price)
    if adv > 0 and trade_usd / adv > rcfg["max_adv_pct"]:
        reason = f"Liquidity veto: {trade_usd/adv*100:.1f}% of ADV (max {rcfg['max_adv_pct']*100:.0f}%)"
        _log_rejection(ticker, reason, trade)
        return False, reason

    # 4. Position size <= 5% AUM
    pos_pct = trade_usd / aum
    if pos_pct > rcfg["max_position_aum_pct"]:
        reason = f"Position size veto: {pos_pct*100:.1f}% AUM (max {rcfg['max_position_aum_pct']*100:.0f}%)"
        _log_rejection(ticker, reason, trade)
        return False, reason

    # 5. Sector <= 25%
    sector_exposure = sum(
        abs(current_weights.get(t, 0))
        for t, s in current_sectors.items()
        if s == ticker_sector
    )
    new_sector_exp = sector_exposure + abs(shares * price / aum)
    if new_sector_exp > rcfg["max_sector_pct"]:
        reason = f"Sector veto: {new_sector_exp*100:.1f}% ({ticker_sector}, max {rcfg['max_sector_pct']*100:.0f}%)"
        _log_rejection(ticker, reason, trade)
        return False, reason

    # 6. Gross exposure and net exposure
    gross = sum(abs(w) for w in current_weights.values())
    new_gross = gross + abs(shares * price / aum)
    if new_gross > rcfg["max_gross_exposure"]:
        reason = f"Gross exposure veto: {new_gross*100:.1f}% (max {rcfg['max_gross_exposure']*100:.0f}%)"
        _log_rejection(ticker, reason, trade)
        return False, reason

    net = sum(current_weights.values())
    new_net = net + (shares * price / aum) * (1 if action in ("BUY", "LONG") else -1)
    if not rcfg["net_min"] <= new_net <= rcfg["net_max"]:
        reason = f"Net exposure veto: {new_net*100:.1f}% (limits [{rcfg['net_min']*100:.0f}%, {rcfg['net_max']*100:.0f}%])"
        _log_rejection(ticker, reason, trade)
        return False, reason

    # 7. Net beta <= 0.20
    new_weights = dict(current_weights)
    sign = 1 if action in ("BUY", "LONG") else -1
    new_weights[ticker] = sign * shares * price / aum
    from portfolio.beta import compute_portfolio_beta
    _, _, net_beta = compute_portfolio_beta(new_weights)
    if abs(net_beta) > rcfg["max_net_beta"]:
        reason = f"Beta veto: net beta {net_beta:.2f} (max |{rcfg['max_net_beta']:.2f}|)"
        _log_rejection(ticker, reason, trade)
        return False, reason

    # 8. Pairwise correlation <= 0.80 with existing positions
    from data.market_data import get_returns
    conn = get_conn()
    new_rets = get_returns(conn, ticker, days=65)
    for existing_ticker in current_weights:
        if existing_ticker == ticker:
            continue
        ext_rets = get_returns(conn, existing_ticker, days=65)
        import pandas as pd
        aligned = pd.concat([new_rets, ext_rets], axis=1).dropna()
        if len(aligned) > 20:
            corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
            if corr > rcfg["max_pairwise_correlation"]:
                conn.close()
                reason = f"Correlation veto: {ticker}/{existing_ticker} corr={corr:.2f} (max {rcfg['max_pairwise_correlation']})"
                _log_rejection(ticker, reason, trade)
                return False, reason
    conn.close()

    logger.info("PRE-TRADE APPROVED: %s %s %d @ $%.2f", action, ticker, shares, price)
    return True, "approved"
