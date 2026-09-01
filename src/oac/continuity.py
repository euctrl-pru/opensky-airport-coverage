"""Was the aerodrome surface actually observed, or merely spanned?

`oac.offsets` measures **reach**: how far before take-off the earliest sample
lies. It says nothing about what happened in between, so a single state vector
at push-back and nothing until the runway scores a perfect 1.000 -- identical
to a receiver that watched every second of the taxi.

This module measures **continuity**: the ground phase is divided into 30 s bins
and each is asked whether any state vector fell inside it. At the feed's 5 s
decimation a bin should hold about six samples, so an empty bin is a reception
gap rather than jitter or one dropped message.

**This cannot be computed from `matched`.** `track_truth.overlap_join` joins on
the *airborne* interval `[t_off, t_land]`, so ground samples are not in it at
all. The join here is against the unfiltered assignment table, on
`[aobt, t_off]` for departures and `[t_land, aibt]` for arrivals.
"""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

#: Bin width in seconds. See the module docstring for why 30 and not 5.
BIN_S = 30

__all__ = ["BIN_S", "ground_occupancy"]


def _side(assign: DataFrame, gt: DataFrame, side: str, bin_s: int) -> DataFrame:
    """Occupancy of one ground phase, one row per flight that has one.

    **The departure side is computed for every flight, measured or not.** Its
    window is ``[aobt, t_off]``, and NM supplies both ends for flights APDF
    never saw: an off-block time and a taxi duration. That window is far looser
    than a measured one -- NM's taxi duration differs from the real one by an
    IQR of 300 s, with only 16.8% inside a minute -- but it is *unbiased*
    (median +13 s), so a median over a few hundred movements is meaningful even
    though a single flight's figure is not.

    The arrival side is measured-only and cannot be otherwise: its window ends
    at the in-block time, and NM has no in-block column at all. There is
    nothing to estimate from.

    The caller keeps the distinction: ``dep_measured`` travels with every row,
    so an aggregate built on estimated windows can be reported separately and
    never mixed with a measured one.
    """
    start, end = ("aobt", "t_off") if side == "dep" else ("t_land", "aibt")

    w = (
        (gt if side == "dep" else gt.filter(F.col("arr_measured")))
        .select("flight_key", "icao24",
                F.col(start).alias("w_start"), F.col(end).alias("w_end"))
        # A non-positive window is bad reference data, not zero coverage. It is
        # dropped here and counted by `oac.aggregate` as n_capture_excluded --
        # keeping it would make bins_total zero and every ratio undefined.
        .filter(F.col("w_end") > F.col("w_start"))
    )

    j = (
        assign.alias("a")
        .join(
            w.alias("w"),
            (F.col("a.icao24") == F.col("w.icao24"))
            & (F.col("a.event_time") >= F.col("w.w_start"))
            & (F.col("a.event_time") < F.col("w.w_end")),
            "inner",
        )
        .select(
            F.col("w.flight_key").alias("flight_key"),
            F.col("w.w_start").alias("w_start"),
            F.col("w.w_end").alias("w_end"),
            F.col("a.event_time").alias("event_time"),
        )
    )

    # Half-open bins anchored at the window start: bin k covers
    # [w_start + k*bin_s, w_start + (k+1)*bin_s).
    binned = j.withColumn(
        "_bin",
        F.floor(
            (F.unix_timestamp("event_time") - F.unix_timestamp("w_start")) / bin_s
        ),
    )

    # Longest silence inside the window, counting the lead-in from the window
    # start and the run-out to its end. A receiver that stops halfway has a real
    # gap even though no two samples straddle it, and measuring only
    # sample-to-sample deltas would report that flight as perfectly covered.
    ordered = Window.partitionBy("flight_key").orderBy("event_time")
    gaps = binned.withColumn(
        "_prev", F.coalesce(F.lag("event_time").over(ordered), F.col("w_start"))
    ).withColumn(
        "_gap", F.unix_timestamp("event_time") - F.unix_timestamp("_prev")
    )

    agg = (
        gaps.groupBy("flight_key")
        .agg(
            F.countDistinct("_bin").alias(f"{side}_bins_seen"),
            F.count(F.lit(1)).alias(f"{side}_n_samples"),
            F.max("_gap").alias("_max_inner_gap"),
            F.max("event_time").alias("_last"),
            F.first("w_end").alias("_w_end"),
        )
        .withColumn(
            f"{side}_max_gap_s",
            F.greatest(
                F.col("_max_inner_gap"),
                F.unix_timestamp("_w_end") - F.unix_timestamp("_last"),
            ).cast("double"),
        )
        .drop("_max_inner_gap", "_last", "_w_end")
    )

    # Left join *from the windows*, not from the samples: a flight never seen on
    # the ground must appear with zero -- which is the finding -- rather than
    # vanish, which reads downstream as the flight not existing.
    total = w.select(
        "flight_key",
        F.ceil(
            (F.unix_timestamp("w_end") - F.unix_timestamp("w_start")) / bin_s
        ).cast("long").alias(f"{side}_bins_total"),
    )
    out = total.join(agg, "flight_key", "left")
    return (
        out.withColumn(
            f"{side}_bins_seen",
            F.coalesce(F.col(f"{side}_bins_seen"), F.lit(0)),
        )
        .withColumn(
            f"{side}_n_samples",
            F.coalesce(F.col(f"{side}_n_samples"), F.lit(0)),
        )
        .withColumn(
            f"{side}_max_gap_s",
            # No samples at all: the gap is the whole window.
            F.coalesce(
                F.col(f"{side}_max_gap_s"),
                (F.col(f"{side}_bins_total") * bin_s).cast("double"),
            ),
        )
    )


def ground_occupancy(assign: DataFrame, gt: DataFrame,
                     bin_s: int = BIN_S) -> DataFrame:
    """One row per ground-truth flight with at least one measured ground phase.

    Flights with neither side measured do not appear at all; the caller
    left-joins this onto the full flight table, so their columns become NULL --
    "not measurable here", which is a different statement from zero coverage
    and must stay distinguishable from it.
    """
    dep = _side(assign, gt, "dep", bin_s)
    arr = _side(assign, gt, "arr", bin_s)
    return dep.join(arr, "flight_key", "outer")
