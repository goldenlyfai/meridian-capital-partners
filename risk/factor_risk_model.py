"""L5: Barra-style cross-sectional factor risk model."""
import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from data.db import get_conn
from data.market_data import get_returns

logger = logging.getLogger(__name__)


def _standardize(series: pd.Series) -> pd.Series:
    """Z-score from 0-100 sector ranks."""
    mu, std = series.mean(), series.std()
    if std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - mu) / std


def build_factor_risk_model(
    scored_df: pd.DataFrame,
    lookback_days: int = 120,
) -> dict:
    """
    Barra-style cross-sectional regression:
      r_i,t = alpha + sum_k beta_k * F_k,i + epsilon_i,t

    Returns:
      factor_returns: DataFrame (days x factors)
      factor_cov: annualized factor covariance matrix
      specific_var: Series of specific variance per stock
    """
    factor_cols = [c for c in scored_df.columns
                   if c in ["momentum", "value", "quality", "growth",
                             "estimate_revisions", "short_interest",
                             "insider_activity", "institutional_flow"]]

    if not factor_cols:
        logger.warning("No factor columns in scored_df")
        return {}

    # Standardize factor exposures
    F = scored_df[factor_cols].apply(_standardize, axis=0)
    tickers = scored_df.index.tolist()

    # Get daily returns for each ticker
    conn = get_conn()
    ret_dict = {}
    for t in tickers:
        rets = get_returns(conn, t, days=lookback_days + 5)
        if not rets.empty:
            ret_dict[t] = rets
    conn.close()

    if not ret_dict:
        return {}

    returns_df = pd.DataFrame(ret_dict).dropna(how="all")
    dates = returns_df.index.tolist()[-lookback_days:]
    returns_df = returns_df.loc[dates]

    factor_returns_list = []

    for date in dates:
        if date not in returns_df.index:
            continue
        r = returns_df.loc[date].dropna()
        common = r.index.intersection(F.index)
        if len(common) < 10:
            continue

        X = F.loc[common].values
        y = r.loc[common].values

        try:
            reg = LinearRegression(fit_intercept=True)
            reg.fit(X, y)
            factor_ret = dict(zip(factor_cols, reg.coef_))
            factor_ret["_date"] = str(date)[:10]
            factor_returns_list.append(factor_ret)
        except Exception:
            continue

    if not factor_returns_list:
        return {}

    factor_returns = pd.DataFrame(factor_returns_list).set_index("_date")
    factor_returns.index.name = "date"

    # Factor covariance (annualized)
    factor_cov = factor_returns.cov() * 252

    # Specific variance per stock
    specific_var = {}
    for t in tickers:
        if t not in returns_df.columns:
            specific_var[t] = 0.04  # default 20% annual vol
            continue
        r = returns_df[t].dropna()
        X_align = F.loc[[t]].values if t in F.index else np.zeros((1, len(factor_cols)))
        # Specific = total vol - explained vol
        total_var = float(r.var() * 252)
        factor_exp = F.loc[t, factor_cols].values if t in F.index else np.zeros(len(factor_cols))
        explained_var = float(factor_exp @ factor_cov.values @ factor_exp)
        specific_var[t] = max(total_var - explained_var, 0.001)

    logger.info("Factor risk model built: %d factors, %d days, %d stocks",
                len(factor_cols), len(factor_returns), len(tickers))

    return {
        "factor_returns": factor_returns,
        "factor_cov": factor_cov,
        "specific_var": pd.Series(specific_var),
        "factor_exposures": F,
    }


def compute_portfolio_risk(
    weights: dict[str, float],
    factor_model: dict,
) -> dict:
    """Decompose portfolio risk into factor vs specific."""
    if not factor_model:
        return {"total_vol": 0.2, "factor_vol": 0.1, "specific_vol": 0.1, "mctr": {}}

    F = factor_model["factor_exposures"]
    F_cov = factor_model["factor_cov"].values
    spec_var = factor_model["specific_var"]

    tickers = [t for t in weights if t in F.index]
    w = np.array([weights[t] for t in tickers])
    X = F.loc[tickers].values

    factor_var = float(w @ X @ F_cov @ X.T @ w)
    specific_var_total = float(sum(
        weights.get(t, 0) ** 2 * float(spec_var.get(t, 0.04))
        for t in tickers
    ))
    total_var = factor_var + specific_var_total
    total_vol = float(np.sqrt(total_var))

    # MCTR: marginal contribution to risk
    port_ret_cov = X @ F_cov @ X.T @ w + np.array([
        weights.get(t, 0) * float(spec_var.get(t, 0.04)) for t in tickers
    ])
    mctr = {t: float(w_i * c / total_vol) if total_vol > 0 else 0
            for t, w_i, c in zip(tickers, w, port_ret_cov)}

    return {
        "total_vol": round(total_vol, 4),
        "factor_vol": round(float(np.sqrt(factor_var)), 4),
        "specific_vol": round(float(np.sqrt(specific_var_total)), 4),
        "factor_var_pct": round(factor_var / total_var * 100 if total_var else 0, 1),
        "specific_var_pct": round(specific_var_total / total_var * 100 if total_var else 0, 1),
        "mctr": mctr,
    }
