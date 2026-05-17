"""L3: Forensic accounting / filing quality analyzer."""
import logging
from typing import Optional

import yaml
from pathlib import Path

from analysis.api_client import get_client
from analysis.cost_tracker import get_tracker
from analysis.cache import get_cached, set_cached
from data.db import get_conn
from data.fundamentals import get_fundamentals

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

SYSTEM_PROMPT = """You are a forensic accounting specialist and equity analyst at a hedge fund.
You identify earnings quality issues, accounting red flags, and balance sheet risks.
Your analysis is quantitative, specific, and actionable. Return ONLY valid JSON."""

ANALYSIS_SCHEMA = {
    "earnings_quality_score": "1-10 (10=highest quality, cash-backed earnings)",
    "balance_sheet_score": "1-10 (10=fortress balance sheet)",
    "red_flags": "list of specific concerns (AR inflation, accruals, debt, etc.)",
    "green_flags": "list of strengths (strong FCF, low accruals, declining debt, etc.)",
    "risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
    "one_line_summary": "single sentence investment-grade assessment",
}


def analyze_filings(ticker: str, force: bool = False) -> Optional[dict]:
    conn = get_conn()
    fund = get_fundamentals(conn, ticker, quarters=8)
    conn.close()

    if fund.empty:
        logger.info("No fundamentals for %s — skipping filing analysis", ticker)
        return None

    artifact_id = f"filings_{ticker}_{fund.iloc[0].get('period', 'unknown')}"

    if not force:
        cached = get_cached("filings", ticker, artifact_id)
        if cached:
            return cached

    # Format metrics table for Claude
    cols = [
        "period", "roe", "roa", "gross_margin", "net_margin",
        "cfo", "net_income", "revenue", "ar_to_revenue", "cfo_to_ni",
        "accruals_ratio", "debt_to_equity", "current_ratio", "fcf_yield",
    ]
    avail = [c for c in cols if c in fund.columns]
    metrics_text = fund[avail].to_string(index=False, float_format=lambda x: f"{x:.3f}" if x else "N/A")

    client = get_client()
    tracker = get_tracker()

    user_prompt = f"""Perform a forensic accounting review of {ticker} using the last 8 quarters of fundamentals.

FUNDAMENTAL DATA (8 QUARTERS):
{metrics_text}

Key indicators to assess:
- Earnings quality: Is CFO tracking NI? (CFO/NI ratio)
- Revenue quality: Is AR growing faster than revenue? (AR/Revenue ratio)
- Accruals: High accruals_ratio predicts underperformance
- Balance sheet: Debt trajectory, current ratio trend
- Margin sustainability: Are margins contracting or expanding?

Return JSON with these fields: {str(ANALYSIS_SCHEMA)}"""

    try:
        text, usage = client.call(SYSTEM_PROMPT, user_prompt, max_tokens=1536)
        tracker.record(usage)
        result = client.extract_json(text)
        if result:
            result["ticker"] = ticker
            set_cached("filings", ticker, artifact_id, result)
            return result
    except Exception as e:
        logger.error("Filing analysis %s: %s", ticker, e)

    return None
