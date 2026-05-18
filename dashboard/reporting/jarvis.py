"""L7: JARVIS — Claude-powered weekly commentary and daily LP letter."""
import json
import logging
import os
from datetime import datetime, date

import yaml
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
AUM = _cfg["fund"]["aum_usd"]
FUND = _cfg["fund"]

import sys as _sys; _sys.path.insert(0, str(ROOT))
from paths import cache_dir as _cache_dir  # noqa: E402
LETTER_CACHE_DIR = _cache_dir() / "letters"

JARVIS_SYSTEM = """You are JARVIS, the AI analyst for Meridian Capital Partners, a long/short equity hedge fund.
You write in a sophisticated, institutional voice — precise, confident, and analytically grounded.
You synthesize quantitative data and qualitative insights into clear, actionable investment narratives.
Your audience is sophisticated limited partners and portfolio managers.
Never use marketing language or platitudes. Be direct, specific, and data-driven."""


def _build_system_snapshot() -> str:
    """Build a ~19KB JSON snapshot of system state for JARVIS context."""
    snapshot = {"generated_at": datetime.utcnow().isoformat()}

    try:
        from portfolio.state import get_positions
        positions = get_positions()
        if not positions.empty:
            snapshot["positions"] = positions[
                ["ticker", "shares", "entry_price", "current_price",
                 "unrealized_pnl", "sector", "signal"]
            ].to_dict("records")
    except Exception:
        pass

    try:
        from risk.risk_state import load
        snapshot["risk"] = load()
    except Exception:
        pass

    try:
        scored_path = ROOT / "output" / "scored_universe_latest.csv"
        if scored_path.exists():
            import pandas as pd
            scored = pd.read_csv(scored_path, index_col="ticker")
            top_longs = scored[scored["signal"] == "LONG"].head(5)[
                ["composite", "sector"]
            ].to_dict()
            top_shorts = scored[scored["signal"] == "SHORT"].tail(5)[
                ["composite", "sector"]
            ].to_dict()
            snapshot["top_longs"] = top_longs
            snapshot["top_shorts"] = top_shorts
    except Exception:
        pass

    return json.dumps(snapshot, default=str)[:19_000]


def generate_lp_letter(force_refresh: bool = False) -> str:
    """Generate today's LP letter. Cached by date."""
    today = date.today().isoformat()
    LETTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = LETTER_CACHE_DIR / f"lp_letter_{today}.txt"

    if cache_path.exists() and not force_refresh:
        return cache_path.read_text()

    snapshot = _build_system_snapshot()
    doc_id = f"MCP-IM-{today[:4]}-{today[5:7]}{today[8:]}"

    from analysis.api_client import get_client
    client = get_client()

    user_prompt = f"""Write a daily LP letter for Meridian Capital Partners.

SYSTEM SNAPSHOT (current portfolio state):
{snapshot}

LETTER FORMAT:
- Letterhead: {FUND['name']} | Delaware | Inception {FUND['inception_date']} | AUM ${AUM/1e6:.0f}M | Doc: {doc_id} | Date: {today}
- Stamp: "CONFIDENTIAL · LIMITED PARTNERS ONLY"
- Salutation: "Dear Limited Partners,"
- Body: 3-4 paragraphs covering:
  1. Market environment and fund positioning
  2. Key portfolio drivers (top performers, detractors)
  3. Risk posture and factor exposures
  4. Outlook and upcoming catalysts
- Signature: "Respectfully submitted, JARVIS / AI Portfolio Intelligence / Meridian Capital Partners"
- Compliance footer: "This letter is confidential and intended solely for limited partners of Meridian Capital Partners LP. Past performance is not indicative of future results. This is not an offer to buy or sell securities."

Write in the JARVIS voice — analytical, precise, institutional. No bullet points in body. Full paragraphs only."""

    try:
        text, _ = client.call(JARVIS_SYSTEM, user_prompt, max_tokens=2048)
        cache_path.write_text(text)
        return text
    except Exception as e:
        logger.error("LP letter generation: %s", e)
        return f"[Letter generation failed: {e}]"


def generate_weekly_commentary() -> str:
    """Generate JARVIS weekly market commentary (fires on configurable weekday)."""
    today = date.today()
    target_day = _cfg["reporting"]["weekly_commentary_day"]
    if today.weekday() != target_day:
        logger.debug("Not commentary day (today=%s, target=%s)", today.weekday(), target_day)
        return ""

    snapshot = _build_system_snapshot()
    from analysis.api_client import get_client
    client = get_client()

    user_prompt = f"""Write a weekly investment commentary for Meridian Capital Partners.

PORTFOLIO STATE:
{snapshot}

Write 4-6 concise paragraphs covering:
1. Week's market themes and macro backdrop
2. Factor performance (what worked, what didn't)
3. Portfolio attribution (long book vs short book)
4. Crowding/positioning risks in the market
5. Outlook for next week — key catalysts, earnings, macro events

Be specific. Name sectors and themes. Use percentages where relevant."""

    try:
        text, _ = client.call(JARVIS_SYSTEM, user_prompt, max_tokens=1500)
        out_path = ROOT / "output" / f"weekly_commentary_{today.isoformat()}.md"
        out_path.write_text(text)
        return text
    except Exception as e:
        logger.error("Weekly commentary: %s", e)
        return f"[Commentary generation failed: {e}]"


def jarvis_chat(user_message: str, history: list[dict] | None = None) -> str:
    """JARVIS interactive chat — answers questions about the portfolio."""
    snapshot = _build_system_snapshot()

    from analysis.api_client import get_client
    client = get_client()

    system = f"""{JARVIS_SYSTEM}

CURRENT PORTFOLIO STATE (as of {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}):
{snapshot}

Answer portfolio manager questions about the fund, positions, risk, and strategy.
Be specific and reference actual data from the system snapshot when available."""

    try:
        text, _ = client.call(system, user_message, max_tokens=1024)
        return text
    except Exception as e:
        return f"JARVIS system error: {e}"
