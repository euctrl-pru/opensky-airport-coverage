"""Aggregate state vectors to H3 cells per aerodrome, for one period.

    ../opdi/.venv310/bin/python scripts/run_h3.py --period 2026

Writes `data/h3_cells_<period>.parquet`: one row per (aerodrome, cell, layer)
that was actually observed. Sparse by construction -- only cells with at least
one position report appear -- which is what keeps it small enough to commit.

Reads the cleaned track table directly. No assignment table and no ground
truth: this asks where reception exists, not which flight it belonged to, so
none of the matching machinery is involved.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from oac._opdi import bootstrap  # noqa: E402

bootstrap()

import osn_sample  # noqa: E402
import provenance  # noqa: E402
import track_methods  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from oac.h3cells import DEFAULT_RES, airport_cells  # noqa: E402

DATA = REPO / "data"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", choices=sorted(track_methods.PERIODS), required=True)
    ap.add_argument("--res", type=int, default=DEFAULT_RES,
                    help=f"H3 resolution (default {DEFAULT_RES})")
    ap.add_argument("--days", nargs="+", default=None)
    args = ap.parse_args()

    osn_sample.load_dotenv()
    spark = osn_sample.build_spark(cores=8, driver_memory="8g")

    p = track_methods.PERIODS[args.period]
    days = args.days or p["days"]
    print(f"period {args.period}: {days}, res {args.res}")

    sv = (
        spark.read.parquet(p["tracks"])
        .filter(F.to_date("event_time").isin(days))
        .select("h3_res_7", "h3_res_12", "on_ground", "baro_altitude_c")
    )
    zones = spark.read.parquet(track_methods.ZONES)

    cells = airport_cells(sv, zones, res=args.res).toPandas()
    cells["period"] = args.period
    cells["res"] = args.res

    DATA.mkdir(parents=True, exist_ok=True)
    name = f"h3_cells_{args.period}.parquet"
    cells.to_parquet(DATA / name, index=False)
    size_mb = (DATA / name).stat().st_size / 1e6
    print(f"wrote {len(cells):,} cells for {cells.icao.nunique()} aerodromes "
          f"to data/{name} ({size_mb:.1f} MB)")
    print(cells.groupby("layer").n.agg(["count", "sum"]).to_string())

    provenance.record(
        DATA, name,
        script="scripts/run_h3.py", argv=sys.argv[1:],
        code_paths=[REPO / "src" / "oac" / "h3cells.py",
                    REPO / "scripts" / "run_h3.py"],
        inputs={"cells": len(cells), "aerodromes": int(cells.icao.nunique()),
                "resolution": args.res},
        input_tables=[p["tracks"]],
        notes=(f"res {args.res}; layers ground (on_ground) and low (airborne "
               f"below 1500 ft). Cruise excluded: one overflight would "
               f"dominate the density."),
    )
    print("provenance recorded")


if __name__ == "__main__":
    main()
