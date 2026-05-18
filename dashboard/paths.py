"""
Centralised path resolution — redirects writable directories to /tmp on Vercel.

On Vercel:  /var/task is read-only; only /tmp is writable.
Locally:    everything lives under the repo root as normal.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # dashboard/


def _on_vercel() -> bool:
    return bool(
        os.getenv("VERCEL")
        or os.getenv("MERIDIAN_DB_PATH", "").startswith("/tmp")
    )


def _base() -> Path:
    return Path("/tmp") if _on_vercel() else ROOT


def output_dir() -> Path:
    p = _base() / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = _base() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_file() -> Path:
    return output_dir() / "run.log"
