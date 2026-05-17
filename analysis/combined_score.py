"""L3: Combined score — 60% quantitative + 40% Claude AI."""
import logging
from typing import Optional

import pandas as pd
import yaml
from pathlib import Path

from analysis.earnings_analyzer import analyze_earnings
from analysis.filing_analyzer import analyze_filings
from analysis.risk_analyzer import analyze_risks
from analysis.insider_analyzer import analyze_insiders

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
QUANT_W = _cfg["analysis"]["combined_score_quant_weight"]
AI_W = _cfg["analysis"]["combined_score_ai_weight"]


def _ai_score_for_ticker(ticker: str) -> Optional[float]:
    """Average available AI analyzer scores (0-100 scale)."""
    scores = []

    earnings = analyze_earnings(ticker)
    if earnings:
        avg = sum([
            earnings.get("management_confidence", 5),
            earnings.get("revenue_guidance", 5),
            earnings.get("margin_trajectory", 5),
        ]) / 3
        scores.append(avg * 10)  # scale 1-10 to 10-100

    filings = analyze_filings(ticker)
    if filings:
        avg = (filings.get("earnings_quality_score", 5) +
               filings.get("balance_sheet_score", 5)) / 2
        scores.append(avg * 10)

    insiders = analyze_insiders(ticker)
    if insiders:
        signal_map = {
            "STRONG_BUY": 90, "BUY": 70, "NEUTRAL": 50,
            "SELL": 30, "STRONG_SELL": 10,
        }
        scores.append(signal_map.get(insiders.get("signal_strength", "NEUTRAL"), 50))

    if not scores:
        return None
    return sum(scores) / len(scores)


def compute_combined_scores(
    scored_df: pd.DataFrame,
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """
    scored_df: output from factors.composite with 'composite' column.
    Returns a copy with 'combined_score' column added.
    """
    df = scored_df.copy()
    target = tickers or df[df["signal"].isin(["LONG", "SHORT"])].index.tolist()

    ai_scores = {}
    for ticker in target:
        ai = _ai_score_for_ticker(ticker)
        ai_scores[ticker] = ai
        if ai is not None:
            logger.info("AI score %s: %.1f", ticker, ai)
        else:
            logger.debug("No AI score for %s — using quant only", ticker)

    combined = []
    for ticker in df.index:
        quant = df.loc[ticker, "composite"]
        ai = ai_scores.get(ticker)
        if ai is not None:
            score = QUANT_W * quant + AI_W * ai
        else:
            score = quant  # 100% quant if no AI
        combined.append(score)

    df["combined_score"] = combined
    return df.sort_values("combined_score", ascending=False)


def get_all_ai_results(ticker: str) -> dict:
    """Return all available AI analyses for a ticker."""
    return {
        "earnings": analyze_earnings(ticker),
        "filings": analyze_filings(ticker),
        "risks": analyze_risks(ticker),
        "insiders": analyze_insiders(ticker),
    }
