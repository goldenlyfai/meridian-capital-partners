"""L3: Token usage and cost tracking with hard ceiling."""
import logging
import threading
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

# Sonnet pricing (per million tokens) — update as needed
SONNET_PRICING = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 3.75,
    "cache_read": 0.30,
}


class CostTracker:
    def __init__(self, ceiling_usd: float | None = None):
        self.ceiling = ceiling_usd or _cfg["analysis"]["cost_ceiling_usd"]
        self._lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_write_tokens = 0
        self.cache_read_tokens = 0
        self.calls = 0

    def record(self, usage: dict):
        with self._lock:
            self.input_tokens += usage.get("input_tokens", 0)
            self.output_tokens += usage.get("output_tokens", 0)
            self.cache_write_tokens += usage.get("cache_creation_input_tokens", 0)
            self.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            self.calls += 1

        cost = self.total_cost_usd()
        logger.info(
            "API call #%d | tokens in=%d out=%d | run cost $%.3f",
            self.calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0), cost,
        )
        if cost > self.ceiling:
            raise RuntimeError(
                f"Cost ceiling exceeded: ${cost:.2f} > ${self.ceiling:.2f}. Aborting."
            )

    def total_cost_usd(self) -> float:
        p = SONNET_PRICING
        return (
            self.input_tokens * p["input"]
            + self.output_tokens * p["output"]
            + self.cache_write_tokens * p["cache_write"]
            + self.cache_read_tokens * p["cache_read"]
        ) / 1_000_000

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_cost_usd": round(self.total_cost_usd(), 4),
        }


_tracker: CostTracker | None = None


def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def reset_tracker():
    global _tracker
    _tracker = CostTracker()
