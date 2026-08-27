"""Per-aerodrome statistics and ranking tables from the committed extracts.

    python scripts/aggregate.py

Pure pandas. No Spark, no S3, no credentials, seconds to run -- which is the
point of the split: changing a percentile, adding a metric or re-cutting the
tiers is a laptop edit, not a two-hour cluster job.

Writes, per period:
    data/airport_stats_<period>.csv      one row per aerodrome, both sides
    data/ranking_tier_a_<period>.csv     APDF aerodromes, ranked on the index
    data/ranking_tier_b_<period>.csv     NM aerodromes, ranked on detection
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import pandas as pd  # noqa: E402

from oac import provenance  # noqa: E402
from oac.aggregate import MIN_N, airport_table, capture  # noqa: E402
from oac.rank import rank_tiers  # noqa: E402

DATA = REPO / "data"
CODE = [REPO / "src" / "oac" / "aggregate.py",
        REPO / "src" / "oac" / "rank.py",
        REPO / "scripts" / "aggregate.py"]


def periods() -> list:
    """Periods with a committed offsets file, newest first."""
    found = sorted(
        (p.stem.replace("flight_offsets_", "")
         for p in DATA.glob("flight_offsets_*.parquet")),
        reverse=True,
    )
    if not found:
        raise SystemExit(
            f"No flight_offsets_*.parquet in {DATA}. Run scripts/run_offsets.py first."
        )
    return found


def airport_names() -> pd.DataFrame:
    p = DATA / "airports.csv"
    if not p.is_file():
        print("  ! data/airports.csv missing -- pages will show ICAO only")
        return pd.DataFrame(columns=["icao", "name", "lat", "lon"])
    return pd.read_csv(p)[["icao", "name", "lat", "lon"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", action="append", default=None,
                    help="restrict to one period (repeatable)")
    args = ap.parse_args()

    names = airport_names()
    todo = args.period or periods()

    for period in todo:
        src = DATA / f"flight_offsets_{period}.parquet"
        if not src.is_file():
            raise SystemExit(f"missing {src}")
        df = pd.read_parquet(src)
        print(f"{period}: {len(df):,} ground-truth flights")

        tbl = airport_table(capture(df))
        tbl = tbl.merge(names, on="icao", how="left")

        stats_name = f"airport_stats_{period}.csv"
        tbl.to_csv(DATA / stats_name, index=False)
        provenance.record(
            DATA, stats_name, script="scripts/aggregate.py", argv=sys.argv[1:],
            code_paths=CODE,
            inputs={"flights": len(df), "aerodromes": len(tbl)},
            notes=f"period={period}. Both sides; suffixes _dep/_arr where they collide.",
        )

        a, b = rank_tiers(tbl)
        for tier, d in (("a", a), ("b", b)):
            name = f"ranking_tier_{tier}_{period}.csv"
            d.to_csv(DATA / name, index=False)
            provenance.record(
                DATA, name, script="scripts/aggregate.py", argv=sys.argv[1:],
                code_paths=CODE,
                inputs={"aerodromes": len(d), "min_n": MIN_N},
                notes=(f"period={period}, tier {tier.upper()}. "
                       + ("Ranked on coverage_index." if tier == "a"
                          else "Ranked on detection_pct; no capture term exists.")),
            )
        print(f"  tier A: {len(a)} aerodromes | tier B: {len(b)} "
              f"(n_gt >= {MIN_N})")

    print("done")


if __name__ == "__main__":
    main()
