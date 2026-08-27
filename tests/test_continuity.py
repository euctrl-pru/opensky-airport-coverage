"""Ground-phase occupancy: what the endpoint metric could not see."""

import datetime as dt

from oac._opdi import bootstrap

bootstrap()

T = dt.datetime


def _gt(spark, rows):
    from pyspark.sql import Row

    return spark.createDataFrame([Row(**r) for r in rows])


def _flight(**over):
    """Off-block 10:00, airborne 10:15-11:05, in-block 11:12.

    Taxi-out is 900 s = 30 bins at 30 s. Taxi-in is 420 s = 14 bins.
    """
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
    from oac.continuity import ground_occupancy

    gt = _gt(spark, gt_rows)
    assign = _assign(spark, samples)
    return {r["flight_key"]: r for r in ground_occupancy(assign, gt).collect()}


def test_one_sample_does_not_cover_the_whole_taxi(spark):
    """The defect this module exists to fix.

    A single state vector at push-back scored 1.000 under the endpoint metric:
    the track's first sample was 900 s before wheels-off, so 'reach' was total.
    Continuity must see one bin out of thirty.
    """
    out = _run(spark, [_flight()], [
        ("abc123", T(2025, 6, 5, 10, 0, 5), "t1"),   # one sample, at push-back
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),     # airborne, not in window
    ])
    r = out["fk1"]
    assert r["dep_bins_total"] == 30
    assert r["dep_bins_seen"] == 1
    assert r["dep_n_samples"] == 1


def test_a_fully_observed_taxi_fills_every_bin(spark):
    """5 s cadence across the whole window: every 30 s bin occupied."""
    samples = [("abc123", T(2025, 6, 5, 10, 0) + dt.timedelta(seconds=5 * i), "t1")
               for i in range(180)]  # 10:00:00 to 10:14:55
    out = _run(spark, [_flight()], samples)
    r = out["fk1"]
    assert r["dep_bins_total"] == 30
    assert r["dep_bins_seen"] == 30
    assert r["dep_n_samples"] == 180


def test_a_gap_in_the_middle_is_counted(spark):
    """Covered for the first 5 minutes, then nothing. 10 bins of 30."""
    samples = [("abc123", T(2025, 6, 5, 10, 0) + dt.timedelta(seconds=5 * i), "t1")
               for i in range(60)]  # 10:00:00 to 10:04:55 = 5 min = 10 bins
    out = _run(spark, [_flight()], samples)
    r = out["fk1"]
    assert r["dep_bins_seen"] == 10
    assert r["dep_bins_total"] == 30
    # The gap runs from the last sample to the end of the window.
    assert r["dep_max_gap_s"] >= 600


def test_arrival_window_is_landing_to_in_block(spark):
    """[ALDT, AIBT] = 11:05 to 11:12 = 420 s = 14 bins."""
    samples = [("abc123", T(2025, 6, 5, 11, 5) + dt.timedelta(seconds=5 * i), "t1")
               for i in range(42)]  # 11:05:00 to 11:08:25 = 7 bins
    out = _run(spark, [_flight()], samples)
    r = out["fk1"]
    assert r["arr_bins_total"] == 14
    assert r["arr_bins_seen"] == 7


def test_a_window_with_no_samples_is_zero_not_null(spark):
    """Never seen on the ground. Must be 0/30, not NULL, and must not divide."""
    out = _run(spark, [_flight()], [
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),  # airborne only
    ])
    r = out["fk1"]
    assert r["dep_bins_total"] == 30
    assert r["dep_bins_seen"] == 0
    assert r["dep_n_samples"] == 0


def test_an_unmeasured_endpoint_has_no_window(spark):
    """No AIBT means no arrival ground phase to measure -- NULL, not zero.

    Two flights, because a one-row fixture whose only `aibt` is None gives
    Spark no type to infer. The second row is the type carrier and the
    control: its arrival side must still be measured.
    """
    out = _run(spark, [
        _flight(aibt=None, arr_measured=False),
        _flight(flight_key="fk2", icao24="def456"),
    ], [
        ("abc123", T(2025, 6, 5, 10, 0, 5), "t1"),
        ("def456", T(2025, 6, 5, 11, 6), "t2"),
    ])
    r = out["fk1"]
    assert r["arr_bins_total"] is None, "no in-block, so no arrival window"
    assert r["dep_bins_total"] == 30, "the departure side is unaffected"
    assert out["fk2"]["arr_bins_total"] == 14, "the measured control is intact"
