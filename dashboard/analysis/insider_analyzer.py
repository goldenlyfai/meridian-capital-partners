"""L3: Insider transaction pattern analyzer."""
import logging
from typing import Optional

from analysis.api_client import get_client
from analysis.cost_tracker import get_tracker
from analysis.cache import get_cached, set_cached
from data.db import get_conn
from data.sec_data import get_insider_transactions

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an insider activity expert at a long/short hedge fund.
You interpret Form 4 SEC filings to distinguish routine selling from meaningful signal-bearing transactions.
CEO/CFO open-market purchases are your highest-conviction buy signals.
Return ONLY valid JSON."""

ANALYSIS_SCHEMA = {
    "signal_strength": "STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL",
    "confidence": "HIGH | MEDIUM | LOW",
    "key_transactions": "list of 3 most important transactions with name, role, amount, date",
    "reasoning": "2-3 sentences interpreting the pattern",
    "one_line_summary": "single sentence signal for portfolio decision",
}


def analyze_insiders(ticker: str, force: bool = False) -> Optional[dict]:
    conn = get_conn()
    txns = get_insider_transactions(conn, ticker, days=90)
    conn.close()

    if not txns:
        logger.info("No insider transactions for %s", ticker)
        return None

    artifact_id = f"insiders_{ticker}_{txns[0]['date'] if txns else 'none'}"
    if not force:
        cached = get_cached("insiders", ticker, artifact_id)
        if cached:
            return cached

    # Format transactions for Claude
    txn_lines = []
    for t in txns[:20]:
        txn_lines.append(
            f"- {t['date']}: {t['insider_name']} ({t['insider_title']}) "
            f"{'BOUGHT' if t['transaction_code']=='P' else 'SOLD'} "
            f"{t['shares']:,.0f} shares @ ${t['price']:.2f} "
            f"(${t.get('amount', t['shares']*t['price']):,.0f})"
            f"{' [CEO/CFO]' if t['is_ceo_cfo'] else ''}"
        )
    txn_text = "\n".join(txn_lines)

    client = get_client()
    tracker = get_tracker()

    user_prompt = f"""Analyze insider transactions for {ticker} over the last 90 days.

FORM 4 TRANSACTIONS:
{txn_text}

Distinguish:
- Routine planned selling (10b5-1 plans, option exercises) vs. conviction buying
- CEO/CFO open-market purchases (highest signal value)
- Cluster buying (multiple insiders buying in same period)

Return JSON: {str(ANALYSIS_SCHEMA)}"""

    try:
        text, usage = client.call(SYSTEM_PROMPT, user_prompt, max_tokens=1024)
        tracker.record(usage)
        result = client.extract_json(text)
        if result:
            result["ticker"] = ticker
            set_cached("insiders", ticker, artifact_id, result)
            return result
    except Exception as e:
        logger.error("Insider analysis %s: %s", ticker, e)

    return None
