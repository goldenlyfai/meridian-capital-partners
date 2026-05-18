"""Shared factor utilities: sector percentile ranking, z-scores."""
import numpy as np
import pandas as pd


def sector_percentile_rank(series: pd.Series, sectors: pd.Series) -> pd.Series:
    """Rank `series` values 0-100 within each GICS sector."""
    result = pd.Series(index=series.index, dtype=float)
    for sector, group in series.groupby(sectors):
        valid = group.dropna()
        if valid.empty:
            result[group.index] = 50.0
            continue
        ranks = valid.rank(pct=True) * 100
        result[valid.index] = ranks
        result[group.index.difference(valid.index)] = 50.0
    return result


def equal_weight_subscore(sub_scores: list[pd.Series]) -> pd.Series:
    """Average a list of sub-factor series, ignoring NaN."""
    df = pd.concat(sub_scores, axis=1)
    return df.mean(axis=1)


def winsorize(series: pd.Series, pct: float = 0.01) -> pd.Series:
    lo = series.quantile(pct)
    hi = series.quantile(1 - pct)
    return series.clip(lo, hi)


def zscore(series: pd.Series) -> pd.Series:
    mu = series.mean()
    std = series.std()
    if std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - mu) / std
