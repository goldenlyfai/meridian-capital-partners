"""L3: Earnings call transcript analyzer."""
import logging
from typing import Optional

import yaml
from pathlib import Path

from analysis.api_client import get_client
from analysis.cost_tracker import get_tracker
from analysis.cache import get_cached, set_cached
from data.db import get_conn
from data.transcripts import get_transcript

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
MAX_CHARS = _cfg["analysis"]["transcript_max_chars"]

SYSTEM_PROMPT = """You are a senior equity analyst at a long/short hedge fund.
Your task is to analyze earnings call transcripts and provide structured investment insights.
You are rigorous, data-driven, and focused on what actually matters for stock performance.
Return ONLY valid JSON — no preamble, no markdown outside the JSON block."""

ANALYSIS_SCHEMA = {
    "management_confidence": "1-10 score",
    "revenue_guidance": "1-10 score (10=strong upward guidance)",
    "margin_trajectory": "1-10 score (10=expanding margins)",
    "competitive_position": "1-10 score",
    "risk_factors": "1-10 score (10=few risks mentioned)",
    "capital_allocation": "1-10 score (buybacks, dividends, investments)",
    "reasoning": "dict with per-category one-sentence rationale",
    "bull_case": "string — strongest bull argument from transcript",
    "bear_case": "string — key risk/concern from transcript",
    "key_quotes": "list of 3-5 verbatim quotes that move the needle",
    "one_line_summary": "single sentence investment takeaway",
}


def analyze_earnings(ticker: str, force: bool = False) -> Optional[dict]:
    conn = get_conn()
    transcript = get_transcript(conn, ticker)
    conn.close()

    if not transcript:
        logger.info("No transcript for %s — skipping earnings analysis", ticker)
        return None

    artifact_id = f"transcript_{hash(transcript[:200])}"

    if not force:
        cached = get_cached("earnings", ticker, artifact_id)
        if cached:
            return cached

    truncated = transcript[:MAX_CHARS]
    client = get_client()
    tracker = get_tracker()

    user_prompt = f"""Analyze this earnings call transcript for {ticker}.

TRANSCRIPT:
{truncated}

Return a JSON object with exactly these fields:
{str(ANALYSIS_SCHEMA)}

Scores are integers 1-10. Be specific and cite evidence from the transcript."""

    try:
        text, usage = client.call(SYSTEM_PROMPT, user_prompt, max_tokens=2048)
        tracker.record(usage)
        result = client.extract_json(text)
        if result:
            result["ticker"] = ticker
            set_cached("earnings", ticker, artifact_id, result)
            return result
    except Exception as e:
        logger.error("Earnings analysis %s: %s", ticker, e)

    return None
