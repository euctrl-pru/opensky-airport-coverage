"""One row per ground-truth flight, ready to aggregate by aerodrome.

`track_score.boundary_offsets` already does the hard half -- the sample
selection, the dominant-track pick, the `extents` join and the signed
subtraction -- and it is **called**, not reimplemented. A second implementation
of the sign convention would look entirely plausible while describing a
different population, and nothing in either output would say so.

Three things are added, none of which is about a boundary:

* the aerodrome keys and block times, joined back from ground truth, so the
  result can be cut per aerodrome and normalised by the flight's own ground
  phase;
* `match_class`, the three-way clean/fragmented/merged classification, so a bad
  coverage number can be attributed to reception or to the segmentation;
* the **undetected flights**. `boundary_offsets` starts from `matched`, and
  `track_truth.overlap_join` is an inner join, so a flight OpenSky never saw
  simply is not there. That is the single strongest coverage signal available,
  and recovering it needs a left join from full ground truth.

Sign convention, stated once and not restated differently anywhere:
``off_s = trk_start - t_off`` (**negative** means the track began before
wheels-off, the good case) and ``land_s = trk_end - t_land`` (**positive**
means it ran on past touchdown, the good case).
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

import track_score

__all__ = ["match_classes", "flight_offsets"]

#: Columns the result carries, in order. Named once so `run_offsets.py` and the
#: aggregation cannot disagree about the schema.
COLUMNS = [
    "flight_key", "icao24", "gt_adep", "gt_ades", "t_source",
    # Per-endpoint provenance. `t_source` is "apdf" only when *both* ends are
    # measured, which mis-classifies an aerodrome whose own side is fully
    # measured but whose traffic comes from uncovered aerodromes -- 26 of them
    # on the 2025 sample, Helsinki and Stuttgart among them.
    "dep_measured", "arr_measured",
    "t_off", "t_land", "aobt", "aibt",
    "track_id", "trk_start", "trk_end", "off_s", "land_s",
    "match_class", "detected",
]


def match_classes(matched: DataFrame) -> DataFrame:
    """`flight_key` -> `match_class`, one row per detected flight.

    The same three mutually exclusive classes `track_score.match_rates` counts,
    evaluated in the same order: a flight that is both merged and fragmented
    counts as **merged**, because merging is the worse failure -- a merged
    flight is unrecoverable downstream while a fragmented one is at least
    present in pieces -- and a flight must not improve its classification by
    also breaking a second way.
    """
    # For each track this flight touches, how many distinct flights that track
    # carries. A flight is merged if ANY of its tracks carries another flight.
    track_flights = matched.groupBy("track_id").agg(
        F.countDistinct("flight_key").alias("n_on_track")
    )
    per_pair = matched.select("flight_key", "track_id").distinct()
    return (
        per_pair.join(track_flights, "track_id")
        .groupBy("flight_key")
        .agg(
            F.countDistinct("track_id").alias("n_tracks"),
            F.max("n_on_track").alias("max_on_track"),
        )
        .select(
            "flight_key",
            F.when(F.col("max_on_track") > 1, F.lit("merged"))
            .when(F.col("n_tracks") > 1, F.lit("fragmented"))
            .otherwise(F.lit("clean"))
            .alias("match_class"),
        )
    )


def flight_offsets(matched: DataFrame, extents: DataFrame, gt: DataFrame) -> DataFrame:
    """One row per ground-truth flight, detected or not.

    `matched` and `extents` must come from the same assignment table.
    `boundary_offsets` raises if they do not, and that check is deliberately not
    duplicated here.

    **`extents` must be built from the unfiltered assignment table.**
    `overlap_join` clips every row into `[t_off, t_land]`, so extents derived
    from `matched` could only land inside the interval: the error would be
    one-sided, what it measured would be sampling cadence rather than boundary
    accuracy, and a merged track -- the failure this study most needs to see --
    would score near zero.
    """
    # `boundary_offsets` restricts itself to `t_source == "apdf"`, which is the
    # conservatism its own docstring records as **open**. This study reports
    # both tiers, so each tier is passed through separately under a relabelled
    # t_source and the real label is restored from `gt` on the way out.
    #
    # Relabelling rather than editing `boundary_offsets`: widening it there
    # would change which flights every already-published V1 number covers.
    # Here the widening is scoped to this study, and the tier still travels
    # with every row so a reader can separate measured from inferred.
    tiers = []
    for is_apdf in (True, False):
        side = matched.filter(
            (F.col("t_source") == "apdf") if is_apdf else (F.col("t_source") != "apdf")
        )
        off = track_score.boundary_offsets(
            side.withColumn("t_source", F.lit("apdf")), extents
        )
        # Materialise before unpersisting: boundary_offsets caches its result
        # and requires the caller to release it, and the union below would
        # otherwise re-derive a plan whose cache has already been dropped.
        tiers.append(
            off.select("flight_key", "track_id", "trk_start", "off_s", "land_s")
            .localCheckpoint(eager=True)
        )
        off.unpersist()

    offs = tiers[0].unionByName(tiers[1])
    # trk_end is not among boundary_offsets' returns; take it from extents,
    # which is where trk_start came from too.
    offs = offs.join(extents.select("track_id", "trk_end"), "track_id", "left")

    return (
        gt.select("flight_key", "icao24", "gt_adep", "gt_ades", "t_source",
                  "dep_measured", "arr_measured",
                  "t_off", "t_land", "aobt", "aibt")
        .join(offs, "flight_key", "left")
        .join(match_classes(matched), "flight_key", "left")
        # An outer join leaves track_id NULL for a flight with no samples.
        # That -- not a NULL offset -- is what "never seen" means: an offset
        # can also be NULL because a timestamp was missing.
        .withColumn("detected", F.col("track_id").isNotNull())
        .select(*COLUMNS)
    )
