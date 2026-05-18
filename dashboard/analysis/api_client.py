"""L3: Anthropic API client with prompt caching, retry, and JSON extraction."""
import json
import logging
import os
import re
import time
from typing import Any

import anthropic
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).parent.parent
_cfg = yaml.safe_load((ROOT / "config.yaml").read_text())


class ClaudeClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = _cfg["analysis"]["model"]
        self.max_retries = 4

    def call(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        use_cache: bool = True,
    ) -> tuple[str, dict]:
        """
        Returns (response_text, usage_dict).
        System prompt uses cache_control: ephemeral for prompt caching.
        """
        system_blocks = [
            {
                "type": "text",
                "text": system,
                **({"cache_control": {"type": "ephemeral"}} if use_cache else {}),
            }
        ]

        for attempt in range(self.max_retries):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=[{"role": "user", "content": user}],
                )
                usage = {
                    "input_tokens": resp.usage.input_tokens,
                    "output_tokens": resp.usage.output_tokens,
                    "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0),
                }
                return resp.content[0].text, usage

            except anthropic.RateLimitError:
                wait = 2 ** attempt
                logger.warning("Rate limit — waiting %ds", wait)
                time.sleep(wait)
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    wait = 2 ** attempt
                    logger.warning("Server error %d — waiting %ds", e.status_code, wait)
                    time.sleep(wait)
                else:
                    raise
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError("Max retries exceeded")

    def extract_json(self, text: str) -> Any:
        """Extract JSON from response — handles raw JSON, fences, and prose-wrapped."""
        # Try ```json ... ``` fences
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if fence:
            try:
                return json.loads(fence.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try raw JSON object or array
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find the first { ... } block
        match = re.search(r"(\{[\s\S]+\})", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning("JSON extraction failed — returning None")
        return None

    def estimate_tokens(self, text: str) -> int:
        """Rough estimate: ~4 chars per token."""
        return len(text) // 4


_client: ClaudeClient | None = None


def get_client() -> ClaudeClient:
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
