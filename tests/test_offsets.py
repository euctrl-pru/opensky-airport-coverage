"""Per-flight offsets: sign convention, detection, and match classification.

The sign convention is the single most invertible thing in this study, and an
inverted one produces a complete, plausible ranking that is exactly backwards.
It is asserted here on concrete seconds rather than on a direction.
"""

import datetime as dt

from oac._opdi import bootstrap

bootstrap()
import track_score  # noqa: E402
import track_truth  # noqa: E402

T = dt.datetime


def _gt(spark, rows):
    from pyspark.sql import Row

    return spark.createDataFrame([Row(**r) for r in rows])


def _one_flight(**over):
    """One APDF-sourced flight: off-block 10:00, airborne 10:15-11:05, in 11:12."""
    row = dict(
        flight_key="fk1", icao24="abc123", gt_adep="EBBR", gt_ades="EGLL",
        t_off=T(2025, 6, 5, 10, 15), t_land=T(2025, 6, 5, 11, 5),
        aobt=T(2025, 6, 5, 10, 0), aibt=T(2025, 6, 5, 11, 12),
        t_source="apdf", dep_measured=True, arr_measured=True,
    )
    row.update(over)
    return row


def _assign(spark, samples):
    from pyspark.sql import Row

    return spark.createDataFrame(
        [Row(icao24=i, event_time=t, track_id=k) for i, t, k in samples]
    )


def _run(spark, gt_rows, samples):
    from oac.offsets import flight_offsets

    gt = _gt(spark, gt_rows)
    assign = _assign(spark, samples)
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)
    return {r["flight_key"]: r for r in flight_offsets(matched, extents, gt).collect()}


def test_track_starting_before_takeoff_has_negative_off_s(spark):
    """The good case. Negative off_s, positive land_s."""
    out = _run(spark, [_one_flight()], [
        ("abc123", T(2025, 6, 5, 10, 5), "t1"),    # taxiing out
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),   # airborne
        ("abc123", T(2025, 6, 5, 11, 10), "t1"),   # taxiing in
    ])
    r = out["fk1"]
    assert r["off_s"] == -600, "10:05 is 600 s before the 10:15 take-off"
    assert r["land_s"] == 300, "11:10 is 300 s after the 11:05 landing"
    assert r["gt_adep"] == "EBBR" and r["gt_ades"] == "EGLL"
    assert r["aobt"] == T(2025, 6, 5, 10, 0)
    assert r["aibt"] == T(2025, 6, 5, 11, 12)
    assert r["detected"] is True
    assert r["match_class"] == "clean"


def test_track_starting_after_takeoff_has_positive_off_s(spark):
    """The bad case, and the one abs() would make indistinguishable."""
    out = _run(spark, [_one_flight()], [
        ("abc123", T(2025, 6, 5, 10, 25), "t1"),
        ("abc123", T(2025, 6, 5, 11, 0), "t1"),
    ])
    r = out["fk1"]
    assert r["off_s"] == 600, "10:25 is 600 s AFTER the 10:15 take-off"
    assert r["land_s"] == -300, "11:00 is 300 s before the 11:05 landing"


def test_flight_never_seen_is_present_and_undetected(spark):
    """The whole point of the left join.

    boundary_offsets starts from `matched`, and overlap_join is an inner join,
    so a flight with no state vectors is invisible to every V1 metric. It is
    the strongest coverage signal there is.
    """
    out = _run(
        spark,
        [_one_flight(), _one_flight(flight_key="fk2", icao24="def456")],
        [("abc123", T(2025, 6, 5, 10, 30), "t1")],
    )
    assert set(out) == {"fk1", "fk2"}
    assert out["fk2"]["detected"] is False
    assert out["fk2"]["off_s"] is None
    assert out["fk2"]["land_s"] is None
    assert out["fk2"]["gt_adep"] == "EBBR", "keys survive so it can be counted"


def test_two_flights_in_one_track_are_classed_merged(spark):
    """Merging is worse than fragmentation and must win the classification."""
    out = _run(spark, [
        _one_flight(),
        _one_flight(flight_key="fk2",
                    t_off=T(2025, 6, 5, 12, 0), t_land=T(2025, 6, 5, 13, 0),
                    aobt=T(2025, 6, 5, 11, 45), aibt=T(2025, 6, 5, 13, 7)),
    ], [
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),
        ("abc123", T(2025, 6, 5, 12, 30), "t1"),
    ])
    assert out["fk1"]["match_class"] == "merged"
    assert out["fk2"]["match_class"] == "merged"


def test_one_flight_in_two_tracks_is_fragmented(spark):
    out = _run(spark, [_one_flight()], [
        ("abc123", T(2025, 6, 5, 10, 20), "t1"),
        ("abc123", T(2025, 6, 5, 10, 50), "t2"),
    ])
    assert out["fk1"]["match_class"] == "fragmented"


def test_merged_beats_fragmented_when_a_flight_is_both(spark):
    """A flight must not improve its class by breaking a second way."""
    out = _run(spark, [
        _one_flight(),
        _one_flight(flight_key="fk2",
                    t_off=T(2025, 6, 5, 12, 0), t_land=T(2025, 6, 5, 13, 0),
                    aobt=T(2025, 6, 5, 11, 45), aibt=T(2025, 6, 5, 13, 7)),
    ], [
        ("abc123", T(2025, 6, 5, 10, 20), "t1"),   # fk1, track 1
        ("abc123", T(2025, 6, 5, 10, 50), "t2"),   # fk1, track 2 -> fragmented
        ("abc123", T(2025, 6, 5, 12, 30), "t2"),   # fk2 on track 2 -> merged
    ])
    assert out["fk1"]["match_class"] == "merged"


def test_nm_inferred_flights_are_kept_with_their_tier(spark):
    """Tier B must reach the output. boundary_offsets filters to apdf itself."""
    out = _run(spark, [
        _one_flight(),
        _one_flight(flight_key="fk2", icao24="def456", gt_adep="LFXX",
                    t_source="nm_inferred", aibt=None,
                    dep_measured=False, arr_measured=False),
    ], [
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),
        # 10:05 is on the ground, outside [t_off, t_land], so it sets the
        # track's extent but cannot match the flight on its own -- the 10:30
        # sample is what overlap_join joins on. Both are needed: the first
        # test in this file relies on exactly the same arrangement.
        ("def456", T(2025, 6, 5, 10, 5), "t2"),
        ("def456", T(2025, 6, 5, 10, 30), "t2"),
    ])
    assert set(out) == {"fk1", "fk2"}
    assert out["fk2"]["t_source"] == "nm_inferred"
    assert out["fk2"]["detected"] is True
    assert out["fk2"]["off_s"] == -600
    assert out["fk2"]["aibt"] is None, "no in-block outside APDF"
    assert out["fk2"]["arr_measured"] is False
    assert out["fk1"]["arr_measured"] is True


def test_extents_come_from_the_full_assignment_not_the_matched_rows(spark):
    """A merged track's real extent falls outside the interval, and must show.

    This is the regression `boundary_error`'s docstring argues at length: taking
    trk_start/trk_end from `matched` makes the error one-sided, because
    overlap_join has already clipped every row into [t_off, t_land]. A track
    spanning two flights would then score near-zero error for the merge.
    """
    out = _run(spark, [_one_flight()], [
        ("abc123", T(2025, 6, 5, 9, 45), "t1"),    # 30 min before take-off
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),   # the only in-interval sample
        ("abc123", T(2025, 6, 5, 11, 35), "t1"),   # 30 min after landing
    ])
    r = out["fk1"]
    assert r["off_s"] == -1800, "the real first sample, not the clipped one"
    assert r["land_s"] == 1800, "the real last sample, not the clipped one"


def test_occupancy_columns_exist_whether_or_not_occupancy_is_given(spark):
    """The schema must not depend on a keyword argument.

    Two callers disagreeing about whether a column exists is a failure three
    stages downstream, in a different script from the one that caused it.
    """
    from oac.offsets import OCCUPANCY_COLUMNS, flight_offsets

    gt = _gt(spark, [_one_flight()])
    assign = _assign(spark, [("abc123", T(2025, 6, 5, 10, 30), "t1")])
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)

    without = flight_offsets(matched, extents, gt)
    assert set(OCCUPANCY_COLUMNS) <= set(without.columns)
    assert without.collect()[0]["dep_bins_total"] is None

    from oac.continuity import ground_occupancy

    occ = ground_occupancy(assign, gt)
    with_occ = flight_offsets(matched, extents, gt, occupancy=occ)
    assert with_occ.columns == without.columns, "same schema either way"


def test_occupancy_reaches_the_flight_row(spark):
    """A track that only appears airborne has an empty taxi-out."""
    from oac.continuity import ground_occupancy
    from oac.offsets import flight_offsets

    gt = _gt(spark, [_one_flight()])
    assign = _assign(spark, [
        ("abc123", T(2025, 6, 5, 10, 5), "t1"),   # one ground sample
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),  # airborne
    ])
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)
    r = flight_offsets(matched, extents, gt,
                       occupancy=ground_occupancy(assign, gt)).collect()[0]

    # Reach says the whole taxi was spanned; continuity says one bin of thirty.
    assert r["off_s"] == -600
    assert r["dep_bins_total"] == 30
    assert r["dep_bins_seen"] == 1
