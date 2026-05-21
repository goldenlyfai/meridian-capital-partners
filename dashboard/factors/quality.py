"""L2: Quality factor — 8 sub-factors + Piotroski F-Score + Altman Z-Score."""
import numpy as np
import pandas as pd

from data.db import get_conn
from data.fundamentals import get_fundamentals
from factors.utils import sector_percentile_rank, equal_weight_subscore, winsorize


def _sf(val) -> float:
    """Safe float — converts None (Postgres NULL) or non-numeric to np.nan."""
    if val is None:
        return np.nan
    try:
        return float(val)
    except (TypeError, ValueError):
        return np.nan


def _piotroski(df: pd.DataFrame) -> int:
    """Compute Piotroski F-Score (0-9) from quarterly fundamentals."""
    if df.empty or len(df) < 2:
        return 5  # neutral

    r0 = df.iloc[0]  # latest
    r1 = df.iloc[1]  # prior quarter

    def v(col, row=r0):
        val = row.get(col)
        return float(val) if val is not None and not np.isnan(float(val or 0)) else None

    score = 0
    # 1. ROA > 0
    roa = v("roa")
    if roa is not None and roa > 0:
        score += 1
    # 2. CFO > 0
    cfo = v("cfo")
    if cfo is not None and cfo > 0:
        score += 1
    # 3. Rising ROA
    roa_prior = v("roa", r1)
    if roa is not None and roa_prior is not None and roa > roa_prior:
        score += 1
    # 4. CFO > NI (quality earnings)
    ni = v("net_income")
    if cfo is not None and ni is not None and cfo > ni:
        score += 1
    # 5. Falling D/E
    de = v("debt_to_equity")
    de_prior = v("debt_to_equity", r1)
    if de is not None and de_prior is not None and de < de_prior:
        score += 1
    # 6. Rising current ratio
    cr = v("current_ratio")
    cr_prior = v("current_ratio", r1)
    if cr is not None and cr_prior is not None and cr > cr_prior:
        score += 1
    # 7. No dilution (shares not increased)
    sh = v("shares_outstanding")
    sh_prior = v("shares_outstanding", r1)
    if sh is not None and sh_prior is not None and sh <= sh_prior:
        score += 1
    # 8. Rising gross margin
    gm = v("gross_margin")
    gm_prior = v("gross_margin", r1)
    if gm is not None and gm_prior is not None and gm > gm_prior:
        score += 1
    # 9. Rising asset turnover
    at_ = v("asset_turnover")
    at_prior = v("asset_turnover", r1)
    if at_ is not None and at_prior is not None and at_ > at_prior:
        score += 1

    return score


def _altman_z(r) -> float | None:
    """Altman Z-Score."""
    try:
        wc = float(r.get("working_capital") or 0)
        ta = float(r.get("total_assets") or 0)
        re = float(r.get("retained_earnings") or 0)
        ebit = float(r.get("ebit") or 0)
        mc = float(r.get("market_cap") or 0)
        tl = float(r.get("total_liabilities") or 0)
        rev = float(r.get("revenue") or 0)
        if ta == 0:
            return None
        z = (1.2 * wc / ta + 1.4 * re / ta + 3.3 * ebit / ta
             + 0.6 * (mc / tl if tl else 0) + 1.0 * rev / ta)
        return z
    except Exception:
        return None


def compute_quality(universe_df: pd.DataFrame) -> pd.Series:
    conn = get_conn()
    tickers = universe_df["ticker"].tolist()
    sectors = universe_df.set_index("ticker")["sector"]

    records = {}
    piotroski_scores = {}
    altman_scores = {}

    for ticker in tickers:
        fund = get_fundamentals(conn, ticker, quarters=12, period_type="quarterly")
        if fund.empty:
            records[ticker] = {}
            continue
        r0 = fund.iloc[0]

        # 8 sub-factors
        roe_vals = fund["roe"].dropna().values
        roe_std = float(np.std(roe_vals)) if len(roe_vals) > 1 else np.nan
        gm_trend = (_sf(fund["gross_margin"].iloc[0]) - _sf(fund["gross_margin"].iloc[3])) \
                   if len(fund) >= 4 else np.nan

        records[ticker] = {
            "roe_stability": -roe_std if not np.isnan(roe_std) else np.nan,
            "gross_margin_level": r0.get("gross_margin", np.nan),
            "gross_margin_trend": gm_trend,
            "debt_to_equity_inv": -(r0.get("debt_to_equity") or np.nan),
            "cfo_to_ni": r0.get("cfo_to_ni", np.nan),
            "accruals_inv": -(r0.get("accruals_ratio") or np.nan),
            "piotroski_f": float(_piotroski(fund)),
            "altman_z": _altman_z(r0) or np.nan,
        }
        piotroski_scores[ticker] = _piotroski(fund)
        altman_scores[ticker] = _altman_z(r0)

    conn.close()

    df = pd.DataFrame(records).T
    df.index.name = "ticker"
    sec = sectors.reindex(df.index)

    ranked = {}
    for col in df.columns:
        ranked[col] = sector_percentile_rank(winsorize(df[col].dropna().reindex(df.index)), sec)

    score = equal_weight_subscore(list(ranked.values()))
    score.name = "quality"

    # Attach raw scores as attributes for dashboard display
    score.piotroski = pd.Series(piotroski_scores)
    score.altman_z = pd.Series(altman_scores)
    return score
