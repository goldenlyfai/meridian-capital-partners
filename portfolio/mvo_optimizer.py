"""L4: Markowitz Mean-Variance Optimizer (SLSQP)."""
import logging

import numpy as np
import pandas as pd

from data.db import get_conn
from data.market_data import get_returns
from portfolio.transaction_costs import estimate_cost_bps

logger = logging.getLogger(__name__)


def _build_covariance(tickers: list[str], days: int = 120) -> np.ndarray:
    conn = get_conn()
    rets = {}
    for t in tickers:
        r = get_returns(conn, t, days=days + 5)
        if not r.empty:
            rets[t] = r
    conn.close()

    df = pd.DataFrame(rets).dropna(how="all")
    df = df.fillna(0)
    cov = df.cov().values * 252  # annualized
    return cov


def _expected_return(score: float) -> float:
    """Map composite score (0-100) linearly to expected annual return (-15% to +15%)."""
    return (score / 100) * 0.30 - 0.15


def mvo_optimize(
    long_candidates: pd.DataFrame,
    short_candidates: pd.DataFrame,
    aum: float,
    cfg: dict,
) -> dict[str, float]:
    """
    Run MVO for long and short books separately, then combine.
    Returns {ticker: weight} — positive for longs, negative for shorts.
    """
    results = {}

    for book, candidates, sign in [
        ("long", long_candidates, +1),
        ("short", short_candidates, -1),
    ]:
        if candidates.empty:
            continue

        tickers = candidates.index.tolist()
        scores = candidates["composite"].values
        n = len(tickers)

        mu = np.array([_expected_return(s) for s in scores])
        cov = _build_covariance(tickers, days=120)

        # Subtract transaction costs from expected returns
        for i, t in enumerate(tickers):
            pos_size = aum * cfg["max_position_pct"]
            cost_bps = estimate_cost_bps(t, pos_size, aum)
            mu[i] -= cost_bps / 10_000

        lam = cfg.get("mvo_risk_aversion", 1.0)
        target = cfg["target_long_gross"] if book == "long" else cfg["target_short_gross"]

        def neg_utility(w):
            port_ret = mu @ w
            port_var = w @ cov @ w
            return -(port_ret - lam * port_var)

        def neg_utility_grad(w):
            return -(mu - 2 * lam * cov @ w)

        # Constraints
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(np.abs(w)) - target},
        ]

        # Bounds: each position [min_pct, max_pct]
        min_pos = cfg.get("min_position_pct", 0.005)
        max_pos = cfg["max_position_pct"]
        bounds = [(min_pos, max_pos)] * n

        # Initial guess: equal weight
        w0 = np.ones(n) * (target / n)

        try:
            try:
                from scipy.optimize import minimize
            except ImportError:
                logger.warning("scipy not available — MVO falling back to conviction optimizer")
                return {}

            result = minimize(
                neg_utility,
                w0,
                method="SLSQP",
                jac=neg_utility_grad,
                bounds=bounds,
                constraints=constraints,
                options={"ftol": 1e-9, "maxiter": 1000},
            )

            if result.success:
                weights = result.x
                for t, w in zip(tickers, weights):
                    results[t] = sign * w
                logger.info("MVO %s book converged: %d positions", book, n)
            else:
                logger.warning("MVO %s book did not converge — using conviction fallback", book)
                return {}

        except Exception as e:
            logger.error("MVO error (%s book): %s", book, e)
            return {}

    return results
