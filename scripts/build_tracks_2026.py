"""Build the 2026 track table from ingested state vectors.

    ../opdi/.venv310/bin/python scripts/build_tracks_2026.py

The 2025 period's tracks came from the production pipeline and the 2024
period's from `adep_ades.py`; neither path builds a *new* research period from
state vectors, so this script does. It applies pipeline step 02's transform
chain -- the same four steps `tracks.py:process_month` applies, in the same
order -- to `research/statevectors/day=...` and writes `research/tracks_2026`.

Replicated rather than called because `process_month` reads a named Iceberg
table for a whole calendar month and appends to `osn_tracks`. This period is
three days living under a different prefix, and redirecting the storage layer
for a one-off would be a larger change than restating four method calls.

**The chain must stay in step with `process_month`.** If step 02 grows a fifth
transform, a table built here silently lacks the column it produces, and the
failure surfaces much later as a missing field in a different script.

Step 02a cleaning is `clean_tracks.py --period 2026`, run afterwards.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from oac._opdi import bootstrap  # noqa: E402

bootstrap()

import osn_sample  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from opdi.config import OPDIConfig  # noqa: E402
from opdi.pipeline.tracks import TrackProcessor  # noqa: E402

DAYS = ["2026-06-05", "2026-06-06", "2026-06-07"]
SRC = "s3a://eurocontrol/opdi/research/statevectors"
OUT = "s3a://eurocontrol/opdi/research/tracks_2026"


def main():
    osn_sample.load_dotenv()
    spark = osn_sample.build_spark(cores=8, driver_memory="8g")

    paths = [f"{SRC}/day={d}" for d in DAYS]
    sv = spark.read.parquet(*paths)
    n_sv = sv.count()
    print(f"{n_sv:,} state vectors over {DAYS}")

    proc = TrackProcessor(spark, OPDIConfig.for_environment("local"))

    # The same four steps process_month applies, in the same order. The
    # intermediate select mirrors its own, which drops the temporary columns
    # the segmentation and H3 stages leave behind.
    original = sv.columns + ["track_id", "h3_res_7", "h3_res_12"]
    df = proc._add_track_id(sv)
    df = proc._add_h3_encoding(df)
    df = df.select(original)
    df = proc._add_cumulative_distance(df)
    df = proc._add_clean_altitude(df, col_name="geo_altitude")
    df = proc._add_clean_altitude(df, col_name="baro_altitude")

    df.write.mode("overwrite").parquet(OUT)
    print(f"wrote {OUT}")

    back = spark.read.parquet(OUT)
    print(f"verified {back.count():,} rows, {back.select('track_id').distinct().count():,} tracks")
    missing = [c for c in ("track_id", "h3_res_7", "h3_res_12",
                           "baro_altitude_c", "geo_altitude_c",
                           "cumulative_distance_nm", "on_ground")
               if c not in back.columns]
    if missing:
        raise SystemExit(f"step 02 chain did not produce {missing} -- the "
                         "replicated chain has drifted from process_month")
    print("all expected columns present")


if __name__ == "__main__":
    main()
