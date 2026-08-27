"""Load the committed extracts. No S3, no Spark, no credentials.

Paths resolve relative to this file, never to the working directory: Quarto
renders each `.qmd` with its own directory as cwd, so an aerodrome page two
levels down would otherwise look in the wrong place.
"""

import json
from pathlib import Path

import pandas as pd

SITE = Path(__file__).resolve().parent
DATA = SITE.parent / "data"

#: Newest first. The first entry is *the* report; the rest are comparison only.
PERIODS = ["2026", "2025", "2024"]

__all__ = ["DATA", "PERIODS", "periods_available", "latest", "load_offsets",
           "load_stats", "load_ranking", "load_airports", "manifest",
           "provenance_rows", "is_verified"]


def periods_available() -> list:
    """Periods with a committed offsets file, newest first."""
    return [p for p in PERIODS if (DATA / f"flight_offsets_{p}.parquet").is_file()]


def latest() -> str:
    """The period every headline number on the site refers to."""
    avail = periods_available()
    if not avail:
        raise FileNotFoundError(
            f"No flight_offsets_*.parquet in {DATA}. Run scripts/run_offsets.py."
        )
    return avail[0]


def load_offsets(period: str = None) -> pd.DataFrame:
    """Per-flight offsets for one period, or all of them concatenated."""
    if period is None:
        frames = [load_offsets(p) for p in periods_available()]
        return pd.concat(frames, ignore_index=True)
    return pd.read_parquet(DATA / f"flight_offsets_{period}.parquet")


def load_stats(period: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"airport_stats_{period}.csv")


def load_ranking(tier: str, period: str = None) -> pd.DataFrame:
    """`tier` is `"a"` or `"b"`. Defaults to the latest period."""
    period = period or latest()
    return pd.read_csv(DATA / f"ranking_tier_{tier}_{period}.csv")


def load_airports() -> pd.DataFrame:
    p = DATA / "airports.csv"
    if not p.is_file():
        return pd.DataFrame(columns=["icao", "name", "lat", "lon"])
    return pd.read_csv(p)


def manifest() -> dict:
    p = DATA / "_manifest.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def is_verified(output: str) -> bool:
    """Whether a committed file has a provenance entry.

    A file with no entry is rendered as **unverified** rather than shown as
    fact. This matters more here than in a paper that re-runs its own analysis:
    the site renders offline by design, and offline rendering is exactly the
    condition under which a stale CSV renders cleanly and says nothing about
    being stale.
    """
    return output in manifest()


def provenance_rows() -> pd.DataFrame:
    """The manifest as a table: one row per committed output."""
    m = manifest()
    if not m:
        return pd.DataFrame(columns=["output", "script", "git_sha", "produced_utc"])
    rows = [
        {
            "output": k,
            "script": v.get("script", ""),
            "git_sha": v.get("git_sha", ""),
            "dirty": v.get("git_dirty", ""),
            "produced_utc": v.get("produced_utc", ""),
            "rows": v.get("inputs", {}).get("ground_truth_flights", ""),
        }
        for k, v in sorted(m.items())
    ]
    return pd.DataFrame(rows)
