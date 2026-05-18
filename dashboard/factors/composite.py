"""L2: Composite score — weighted blend of all 8 factors, sector re-ranked."""
import logging

import pandas as pd

from factors.utils import sector_percentile_rank, winsorize
from factors.regime_weights import get_weights

logger = logging.getLogger(__name__)

FACTOR_MODULES = {
    "momentum": "factors.momentum",
    "value": "factors.value",
    "quality": "factors.quality",
    "growth": "factors.growth",
    "estimate_revisions": "factors.revisions",
    "short_interest": "factors.short_interest",
    "insider_activity": "factors.insider",
    "institutional_flow": "factors.institutional",
}

COMPUTE_FN = {
    "momentum": "compute_momentum",
    "value": "compute_value",
    "quality": "compute_quality",
    "growth": "compute_growth",
    "estimate_revisions": "compute_revisions",
    "short_interest": "compute_short_interest",
    "insider_activity": "compute_insider",
    "institutional_flow": "compute_institutional",
}


def compute_all_factors(universe_df: pd.DataFrame) -> pd.DataFrame:
    """Compute all 8 factor scores and return a DataFrame indexed by ticker."""
    import importlib
    results = {}
    for factor, module_path in FACTOR_MODULES.items():
        try:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, COMPUTE_FN[factor])
            score = fn(universe_df)
            results[factor] = score
            logger.info("Factor computed: %s", factor)
        except Exception as e:
            logger.error("Factor %s failed: %s", factor, e)
            results[factor] = pd.Series(50.0, index=universe_df["ticker"].tolist(), name=factor)

    return pd.DataFrame(results)


def compute_composite(
    factor_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    vix: float | None = None,
) -> pd.DataFrame:
    """
    Blend factor scores into composite, re-rank within sector.
    Returns scored_df with all sub-factor scores + composite + LONG/SHORT flag.
    """
    weights = get_weights(vix=vix)
    sectors = universe_df.set_index("ticker")["sector"]

    composite = pd.Series(0.0, index=factor_df.index)
    total_weight = 0.0
    for factor, w in weights.items():
        if factor in factor_df.columns:
            composite += factor_df[factor].fillna(50.0) * w
            total_weight += w

    if total_weight > 0:
        composite /= total_weight

    # Re-rank within sector
    sec = sectors.reindex(composite.index)
    composite_ranked = sector_percentile_rank(composite, sec)

    factor_df = factor_df.copy()
    factor_df["composite"] = composite_ranked

    # Long/Short flags
    top_quintile = composite_ranked >= 80
    bot_quintile = composite_ranked <= 20
    factor_df["signal"] = "NEUTRAL"
    factor_df.loc[top_quintile, "signal"] = "LONG"
    factor_df.loc[bot_quintile, "signal"] = "SHORT"

    # Merge universe info
    uni = universe_df.set_index("ticker")[["company_name", "sector", "sub_industry"]]
    result = factor_df.join(uni, how="left")
    result.index.name = "ticker"

    logger.info(
        "Composite: %d LONG candidates, %d SHORT candidates",
        top_quintile.sum(), bot_quintile.sum(),
    )
    return result.sort_values("composite", ascending=False)
