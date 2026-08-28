"""Produce the per-flight offsets table for one period, on the OSN cluster.

    ../opdi/.venv310/bin/python scripts/run_offsets.py --period 2025

Reads cleaned tracks for the sample days, segments them with the A8
``recommended`` rule, and writes one row per ground-truth flight to
``data/flight_offsets_<period>.parquet``.

**The assignment table is written, read back and deleted within one run.** One
assignment table is ~0.31 GB and the bucket is shared and quota'd, so peak
footprint is one, not several. That discipline lives in
``track_methods.run_arm``, which this script calls rather than copies --
including the release on the failure path, which is what stops a crash
orphaning a table.

**Extents come from the unfiltered assignment table.** ``run_arm`` computes
them that way. Never recompute them from ``matched``, which ``overlap_join``
has already clipped to ``[t_off, t_land]``: the error would become one-sided
and a merged track would score near-zero for the merge.

Sign convention, stated once: ``off_s = trk_start - ATOT`` (negative is good)
and ``land_s = trk_end - ALDT`` (positive is good).
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
import track_truth  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from oac.continuity import ground_occupancy  # noqa: E402
from oac.offsets import flight_offsets  # noqa: E402
from oac.truth import airports_in_bbox  # noqa: E402
from opdi.config import OPDIConfig  # noqa: E402
from opdi.pipeline.segmentation import SegmentationParams  # noqa: E402

#: A8 -- the study's segmentation, and opdi's default since 2026-08-27.
ARM = "recommended"
DATA = REPO / "data"


def build_params():
    """Engine parameters from the pipeline's own config, not from literals."""
    cfg = OPDIConfig().segmentation
    return SegmentationParams(
        gap_minutes=cfg.gap_minutes,
        low_alt_gap_minutes=cfg.low_alt_gap_minutes,
        low_alt_ft=cfg.low_alt_ft,
        ground_dwell_minutes=cfg.ground_dwell_minutes,
        turnaround_max_height_ft=cfg.turnaround_max_height_ft,
        turnaround_max_speed_kt=cfg.turnaround_max_speed_kt,
        descent_floor_ft=cfg.descent_floor_ft,
    )


def restrict_to_bbox(spark, gt):
    """Drop ground-truth flights with neither end inside the ingested area.

    Kept when **either** end is in the bbox, not both: a Frankfurt-to-Dubai
    flight has a measurable departure and an unmeasurable arrival, and dropping
    it would throw away a real departure observation. The aggregation excludes
    out-of-bbox aerodromes per side, so OMDB never reaches a ranking table
    while EDDF's departure still counts.

    Returns ``(gt, airports_df)``.
    """
    apts = airports_in_bbox(spark, track_methods.AIRPORTS).cache()
    codes = [r["icao"] for r in apts.select("icao").collect()]
    keep = F.col("gt_adep").isin(codes) | F.col("gt_ades").isin(codes)
    return gt.filter(keep), apts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", choices=sorted(track_methods.PERIODS), required=True)
    ap.add_argument("--days", nargs="+", default=None,
                    help="override the period's day list")
    ap.add_argument("--keep-assignments", action="store_true",
                    help="leave the assignment table on S3 (default: delete)")
    # `osn_sample.RESEARCH_EXECUTORS` defaults to 4, well under the ~12 the
    # namespace allows. That default suits a quick probe; these jobs read a
    # 150M-row table and are worth the full allocation.
    ap.add_argument("--executors", type=int, default=10,
                    help="K8s executors to request (default 10, ceiling ~12)")
    args = ap.parse_args()

    # Python buffers stdout when it is redirected to a file, so a long run
    # shows the JVM's stderr progress bars and none of its own lines until it
    # exits -- which makes a healthy job indistinguishable from a hung one.
    sys.stdout.reconfigure(line_buffering=True)

    osn_sample.load_dotenv()
    # Set before build_spark: the module reads this global when it builds the
    # K8s session, so assigning after the fact has no effect.
    osn_sample.RESEARCH_EXECUTORS = args.executors
    print(f"requesting {args.executors} executors")
    spark = osn_sample.build_spark(cores=8, driver_memory="8g")
    s3 = track_methods.s3_client()

    p = track_methods.PERIODS[args.period]
    days = args.days or p["days"]
    print(f"period {args.period}: {days}")

    sv = spark.read.parquet(p["tracks"]).filter(F.to_date("event_time").isin(days))
    sv = track_methods.attach_airport_context(spark, sv).cache()
    gt = track_truth.load_flight_intervals(spark, p["months"], days)
    gt, apts = restrict_to_bbox(spark, gt)
    gt = gt.cache()

    n_sv, n_gt = sv.count(), gt.count()
    print(f"{n_sv:,} samples, {n_gt:,} ground-truth flights with an end in bbox")

    def score(matched, extents, assign):
        # `assign` is the unfiltered assignment table. Ground-phase occupancy
        # cannot come from `matched`, which `overlap_join` has restricted to
        # the airborne interval -- taxi samples are not in it at all.
        occ = ground_occupancy(assign, gt)
        return flight_offsets(matched, extents, gt, occupancy=occ).toPandas()

    df, meta = track_methods.run_arm(
        spark, s3, ARM, args.period, sv, gt, build_params(),
        args.keep_assignments, score=score, path_arm=f"coverage_{args.period}",
    )
    df["period"] = args.period

    DATA.mkdir(parents=True, exist_ok=True)
    name = f"flight_offsets_{args.period}.parquet"
    df.to_parquet(DATA / name, index=False)
    print(f"wrote {len(df):,} rows to data/{name}")

    # The aerodrome names the site needs, so it never has to reach S3.
    apts.toPandas().to_csv(DATA / "airports.csv", index=False)

    provenance.record(
        DATA, name,
        script="scripts/run_offsets.py", argv=sys.argv[1:],
        code_paths=[REPO / "src" / "oac" / "offsets.py",
                    REPO / "src" / "oac" / "continuity.py",
                    REPO / "src" / "oac" / "truth.py",
                    REPO / "scripts" / "run_offsets.py"],
        inputs={"state_vectors": n_sv, "ground_truth_flights": n_gt,
                "assignment_objects": meta["assign_objects"],
                "assignment_bytes": meta["assign_bytes"]},
        input_tables=[p["tracks"]],
        notes=(f"arm={ARM}, days={days}. Signed: off_s = trk_start - ATOT "
               "(negative = before wheels-off), land_s = trk_end - ALDT "
               "(positive = past touchdown). Ground occupancy binned at "
               f"{ground_occupancy.__defaults__[0]} s."),
    )
    print("provenance recorded")


if __name__ == "__main__":
    main()
