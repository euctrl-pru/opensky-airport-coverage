"""Load the committed extracts. No S3, no Spark, no credentials.

Paths resolve relative to this file, never to the working directory: Quarto
renders each `.qmd` with its own directory as cwd, so an aerodrome page two
levels down would otherwise look in the wrong place.
"""

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

# No pyspark anywhere beneath this import; see `oac.provenance`.
from oac.provenance import POSITION_FILTER_NOTE

SITE = Path(__file__).resolve().parent
DATA = SITE.parent / "data"

#: Periods are **discovered from disk**, not listed here.
#:
#: An earlier version filtered a hardcoded list, which failed in the one way
#: that matters: a period not on the list produced no error, no warning and a
#: page with no charts and no tables on it. Anything that adds a period --
#: a new sample, a re-run under a different label -- should appear by being
#: present, not by also being remembered here.

__all__ = ["DATA", "DAYS", "sample_days", "periods_available", "latest",
           "load_offsets", "load_slice", "load_fleet", "load_stats",
           "load_ranking", "load_airports", "manifest", "provenance_rows",
           "is_verified", "POSITION_FILTER_MARK", "periods_without_filter"]

#: The note the extraction scripts stamp when they drop state vectors carrying
#: no position, imported from the module that writes it rather than retyped.
#:
#: Matched rather than assumed, because the code and the committed data move
#: separately: the filter landed as a code change, and every extract produced
#: before it still counts those reports. A page stating the filter as fact
#: while showing figures that predate it is the failure the manifest exists to
#: catch.
POSITION_FILTER_MARK = POSITION_FILTER_NOTE

#: The days each period samples. Lives here rather than on a page because two
#: pages state it and a reader who finds them disagreeing cannot tell which is
#: right. Unlike the periods themselves this cannot be discovered from disk --
#: the committed extracts carry no calendar -- so it is written down once.
DAYS = {
    "2026": "5–7 June 2026",
    "2025": "5–7 June 2025",
    "2024": "5–7 June 2024",
}


def sample_days(period: str) -> str:
    """The days `period` samples, or a bare question mark if unrecorded."""
    return DAYS.get(period, "?")


def periods_available() -> list:
    """Periods with a committed offsets file, newest first.

    Newest first is what makes `latest()` correct, and every headline number
    on the site is `latest()`.
    """
    return sorted(
        (p.stem.replace("flight_offsets_", "")
         for p in DATA.glob("flight_offsets_*.parquet")),
        reverse=True,
    )


def latest() -> str:
    """The period every headline number on the site refers to."""
    avail = periods_available()
    if not avail:
        raise FileNotFoundError(
            f"No flight_offsets_*.parquet in {DATA}. Run scripts/run_offsets.py."
        )
    return avail[0]


@lru_cache(maxsize=None)
def load_slice(icao: str) -> pd.DataFrame:
    """One aerodrome's flights, both sides, all periods, capture precomputed.

    Written by `scripts/gen_pages.py`. A page reads this and nothing else --
    reading the full per-flight table per page is what made the render
    quadratic in aerodrome count.
    """
    p = DATA / "pages" / f"{icao}.parquet"
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} missing. Run scripts/gen_pages.py before rendering."
        )
    return pd.read_parquet(p)


@lru_cache(maxsize=None)
def load_fleet() -> pd.DataFrame:
    """Fleet-wide capture for the latest period: the ECDF reference line."""
    p = DATA / "pages" / "_fleet.parquet"
    return pd.read_parquet(p) if p.is_file() else pd.DataFrame(
        columns=["dep_capture", "arr_capture"]
    )


def load_offsets(period: str = None) -> pd.DataFrame:
    """Per-flight offsets for one period, or all of them concatenated."""
    if period is None:
        frames = [load_offsets(p) for p in periods_available()]
        return pd.concat(frames, ignore_index=True)
    return pd.read_parquet(DATA / f"flight_offsets_{period}.parquet")


@lru_cache(maxsize=None)
def load_stats(period: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"airport_stats_{period}.csv")


@lru_cache(maxsize=None)
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


def periods_without_filter() -> list:
    """Periods whose committed offsets predate the position filter.

    Empty once every extract has been regenerated, which is what makes the
    warning on the about page disappear by itself rather than by someone
    remembering to delete it.

    A period with no manifest entry counts as unfiltered. That is the
    conservative reading and the correct one: an unverified extract cannot
    evidence the filter, and treating silence as compliance would restore the
    overclaim in the one case where there is least reason to trust it.
    """
    m = manifest()
    out = []
    for period in periods_available():
        entry = m.get(f"flight_offsets_{period}.parquet")
        notes = (entry or {}).get("notes", "")
        if POSITION_FILTER_MARK not in notes:
            out.append(period)
    return out


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
