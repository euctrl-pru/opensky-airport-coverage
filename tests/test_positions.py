"""A state vector with no position is not a position report.

The filter is applied at read time in every extraction script, so these tests
work at two levels: the predicate itself, and the metric that was wrong
without it.
"""

import datetime as dt

import pytest

from oac._opdi import bootstrap

bootstrap()

from oac.positions import position_share, positioned  # noqa: E402

T = dt.datetime


def _rows(spark, rows):
    from pyspark.sql import Row

    return spark.createDataFrame([Row(**r) for r in rows])


def _sv(spark):
    """Four reports: two positioned, one missing lon, one missing both."""
    return _rows(spark, [
        dict(icao24="abc123", event_time=T(2026, 6, 5, 10, 0, 0),
             lat=50.9, lon=4.48),
        dict(icao24="abc123", event_time=T(2026, 6, 5, 10, 0, 5),
             lat=50.9, lon=None),
        dict(icao24="abc123", event_time=T(2026, 6, 5, 10, 0, 10),
             lat=None, lon=None),
        dict(icao24="abc123", event_time=T(2026, 6, 5, 10, 0, 15),
             lat=50.91, lon=4.49),
    ])


def test_only_reports_carrying_a_position_survive(spark):
    kept = positioned(_sv(spark)).collect()
    assert len(kept) == 2
    assert all(r["lat"] is not None and r["lon"] is not None for r in kept)


def test_half_a_position_is_no_position(spark):
    """A lat with no lon cannot be placed, so it is not a position.

    Filtering on `lat` alone would keep it and then produce a null H3 cell
    downstream, which is a crash rather than a wrong number.
    """
    kept = [r["event_time"].second for r in positioned(_sv(spark)).collect()]
    assert 5 not in kept


def test_a_frame_without_the_columns_raises_rather_than_passing_through(spark):
    """A silent no-op would restore the old behaviour everywhere at once.

    Every number on the site would move back with nothing to say why, which
    is precisely the failure the filter exists to end.
    """
    df = _rows(spark, [dict(icao24="abc123", event_time=T(2026, 6, 5, 10, 0))])
    with pytest.raises(ValueError, match="lat"):
        positioned(df)


def test_the_share_is_reported_rather_than_inferred(spark):
    share = position_share(_sv(spark))
    assert share == {"rows": 4, "positioned": 2, "dropped": 2, "share": 0.5}


def test_an_empty_frame_does_not_divide_by_zero(spark):
    import math

    empty = positioned(_sv(spark)).filter("lat > 90")
    share = position_share(empty)
    assert share["rows"] == 0 and math.isnan(share["share"])


# --- the metric that was wrong without it --------------------------------

def _gt(spark):
    """One arrival: lands 10:00, in-block 10:06. A six-minute taxi-in."""
    from pyspark.sql import Row

    return spark.createDataFrame([Row(
        flight_key="f1", icao24="abc123",
        aobt=T(2026, 6, 5, 9, 0), t_off=T(2026, 6, 5, 9, 12),
        t_land=T(2026, 6, 5, 10, 0), aibt=T(2026, 6, 5, 10, 6),
        dep_measured=True, arr_measured=True,
    )])


def _assign(spark, positions):
    """Reports every 30 s across the taxi-in; `positions` says which have one.

    The schema is declared rather than inferred: the case that matters most
    here is a taxi where *every* report lacks a position, and an all-null
    column gives Spark nothing to infer from.
    """
    from pyspark.sql.types import (DoubleType, StringType, StructField,
                                   StructType, TimestampType)

    schema = StructType([
        StructField("icao24", StringType()),
        StructField("event_time", TimestampType()),
        StructField("lat", DoubleType()),
        StructField("lon", DoubleType()),
    ])
    rows = [
        ("abc123",
         T(2026, 6, 5, 10, 0) + dt.timedelta(seconds=30 * i),
         50.9 if has_pos else None,
         4.48 if has_pos else None)
        for i, has_pos in enumerate(positions)
    ]
    return spark.createDataFrame(rows, schema)


def test_a_taxi_seen_only_without_positions_now_scores_zero(spark):
    """The Istanbul shape, reduced to one flight.

    Twelve reports spanning the whole taxi-in, none of them carrying a
    position. Before the filter this scored a full twelve bins of twelve and
    a signal near 1.000 at an aerodrome that receives nothing at all from its
    surface. It must now score zero.
    """
    from oac.continuity import ground_occupancy

    assign = _assign(spark, [False] * 12)
    got = ground_occupancy(positioned(assign), _gt(spark)).collect()[0]
    assert got["arr_bins_seen"] == 0
    assert got["arr_n_samples"] == 0
    assert got["arr_bins_total"] == 12


def test_positioned_reports_are_still_counted(spark):
    """The filter must not quietly zero a genuinely observed taxi."""
    from oac.continuity import ground_occupancy

    assign = _assign(spark, [True] * 12)
    got = ground_occupancy(positioned(assign), _gt(spark)).collect()[0]
    assert got["arr_bins_seen"] == 12
    assert got["arr_n_samples"] == 12


def test_a_mixed_taxi_counts_only_the_positioned_half(spark):
    """Six positioned then six not: half the taxi, and a gap that says so."""
    from oac.continuity import ground_occupancy

    assign = _assign(spark, [True] * 6 + [False] * 6)
    got = ground_occupancy(positioned(assign), _gt(spark)).collect()[0]
    assert got["arr_bins_seen"] == 6
    assert got["arr_n_samples"] == 6
    # Last positioned report is at 10:02:30; the window ends at 10:06.
    assert got["arr_max_gap_s"] == pytest.approx(210.0)
