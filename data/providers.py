"""Provider abstraction — routes to best available data source."""
import logging
import os

logger = logging.getLogger(__name__)


class DataProviders:
    def __init__(self):
        self.polygon_key = os.getenv("POLYGON_API_KEY")
        self.fmp_key = os.getenv("FMP_API_KEY")
        self.fred_key = os.getenv("FRED_API_KEY")

        self.use_polygon = bool(self.polygon_key)
        self.use_fmp = bool(self.fmp_key)
        self.use_fred = bool(self.fred_key)

        self._log_active()

    def _log_active(self):
        if self.use_polygon:
            logger.info("Using Polygon for prices")
        else:
            logger.info("Falling back to yfinance for prices")

        if self.use_fmp:
            logger.info("Using FMP for transcripts + structured financials")
        else:
            logger.info("FMP not configured — transcripts unavailable")

        if self.use_fred:
            logger.info("Using FRED for macro data (yield curve, credit spreads)")
        else:
            logger.info("FRED not configured — using VIX proxy for tail risk")


_providers: DataProviders | None = None


def get_providers() -> DataProviders:
    global _providers
    if _providers is None:
        _providers = DataProviders()
    return _providers
