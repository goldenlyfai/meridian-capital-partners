"""L3: 10-K Risk Factors analyzer — material vs. boilerplate."""
import logging
import os
from typing import Optional
from pathlib import Path

import yaml
import requests

from analysis.api_client import get_client
from analysis.cost_tracker import get_tracker
from analysis.cache import get_cached, set_cached
from data.sec_data import HEADERS, RATE_LIMIT_SLEEP

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
MAX_CHARS = _cfg["analysis"]["risk_factors_max_chars"]

SYSTEM_PROMPT = """You are a risk analysis specialist at a long/short hedge fund.
You read SEC 10-K Risk Factors sections and distinguish material risks from legal boilerplate.
Your job is to identify what could actually hurt (or help) this investment thesis.
Return ONLY valid JSON."""

ANALYSIS_SCHEMA = {
    "new_risks": "list of risks not typically present in this sector — novel or company-specific",
    "material_risks": "list of top 5 risks that could materially impact stock price",
    "boilerplate_percentage": "estimated % of text that is standard legal boilerplate (0-100)",
    "risk_severity": "LOW | MEDIUM | HIGH | CRITICAL",
    "one_line_summary": "single sentence: what investors must know about this company's risks",
}


def _fetch_10k_risk_factors(ticker: str) -> Optional[str]:
    """Try to get Risk Factors from cached SEC filing."""
    cache_path = ROOT / "cache" / "sec_filings" / f"{ticker}_10k_risks.txt"
    if cache_path.exists():
        return cache_path.read_text()[:MAX_CHARS]
    return None


def analyze_risks(ticker: str, force: bool = False) -> Optional[dict]:
    risk_text = _fetch_10k_risk_factors(ticker)
    if not risk_text:
        logger.info("No 10-K risk factors cached for %s", ticker)
        return None

    artifact_id = f"risks_{hash(risk_text[:500])}"
    if not force:
        cached = get_cached("risks", ticker, artifact_id)
        if cached:
            return cached

    client = get_client()
    tracker = get_tracker()

    user_prompt = f"""Analyze the Risk Factors section from {ticker}'s most recent 10-K filing.

RISK FACTORS TEXT:
{risk_text[:MAX_CHARS]}

Identify:
1. Novel/company-specific risks (not generic sector boilerplate)
2. Top 5 material risks that could move the stock
3. Estimate what % is boilerplate legal language
4. Overall risk severity

Return JSON: {str(ANALYSIS_SCHEMA)}"""

    try:
        text, usage = client.call(SYSTEM_PROMPT, user_prompt, max_tokens=1536)
        tracker.record(usage)
        result = client.extract_json(text)
        if result:
            result["ticker"] = ticker
            set_cached("risks", ticker, artifact_id, result)
            return result
    except Exception as e:
        logger.error("Risk analysis %s: %s", ticker, e)

    return None
