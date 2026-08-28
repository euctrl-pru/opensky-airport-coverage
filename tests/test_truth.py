import datetime as dt

from oac._opdi import bootstrap

bootstrap()
import track_truth  # noqa: E402


def _apdf_row(**over):
    """Only the columns `load_apdf_times` reads.

    The real APDF extract has 24, most of them nullable ring-crossing fields;
    an all-None column defeats Spark's schema inference and none of them is
    under test here.
    """
    row = dict(
        # The Samad flight id -- the key APDF is joined on.
        ID=1,
        AP_C_FLTID="TST123 ", SRC_PHASE="DEP",
        ADEP_ICAO="EBBR", ADES_ICAO="EGLL",
        MVT_TIME_UTC=dt.datetime(2025, 6, 5, 10, 15, 0),
        BLOCK_TIME_UTC=dt.datetime(2025, 6, 5, 10, 0, 0),
    )
    row.update(over)
    return row


def _write_apdf(spark, tmp_path, rows):
    from pyspark.sql import Row

    base = str(tmp_path / "ref")
    spark.createDataFrame([Row(**r) for r in rows]).write.parquet(
        f"{base}/apdf_202506.parquet"
    )
    return base


def test_departure_block_time_is_aobt_arrival_is_aibt(spark, tmp_path):
    """APDF has no literal AOBT/AIBT column.

    BLOCK_TIME_UTC is off-block on a DEP row and in-block on an ARR row -- the
    same SRC_PHASE discrimination already applied to MVT_TIME_UTC.
    """
    base = _write_apdf(spark, tmp_path, [
        _apdf_row(),
        _apdf_row(SRC_PHASE="ARR",
                  MVT_TIME_UTC=dt.datetime(2025, 6, 5, 11, 5, 0),
                  BLOCK_TIME_UTC=dt.datetime(2025, 6, 5, 11, 12, 0)),
    ])
    dep, arr = track_truth.load_apdf_times(spark, ["202506"], reference_base=base)

    d = dep.collect()
    assert len(d) == 1
    assert d[0]["atot"] == dt.datetime(2025, 6, 5, 10, 15, 0)
    assert d[0]["aobt"] == dt.datetime(2025, 6, 5, 10, 0, 0)
    assert d[0]["aobt"] < d[0]["atot"], "off-block precedes take-off"

    a = arr.collect()
    assert len(a) == 1
    assert a[0]["aldt"] == dt.datetime(2025, 6, 5, 11, 5, 0)
    assert a[0]["aibt"] == dt.datetime(2025, 6, 5, 11, 12, 0)
    assert a[0]["aibt"] > a[0]["aldt"], "in-block follows landing"


def test_block_times_reach_the_flight_interval_table(spark, tmp_path):
    """aobt/aibt must survive both joins -- they are the capture denominator."""
    from pyspark.sql import Row

    base = _write_apdf(spark, tmp_path, [
        _apdf_row(),
        _apdf_row(SRC_PHASE="ARR",
                  MVT_TIME_UTC=dt.datetime(2025, 6, 5, 11, 5, 0),
                  BLOCK_TIME_UTC=dt.datetime(2025, 6, 5, 11, 12, 0)),
    ])
    spark.createDataFrame([Row(
        ID=1,
        AIRCRAFT_ADDRESS="ABC123", AIRCRAFT_ID="TST123", ADEP="EBBR",
        ADES="EGLL", AOBT_3=dt.datetime(2025, 6, 5, 10, 0, 0),
        ARVT_3=dt.datetime(2025, 6, 5, 11, 5, 0), TAXI_TIME_3=15.0,
    )]).write.parquet(f"{base}/flights_202506.parquet")

    gt = track_truth.load_flight_intervals(
        spark, ["202506"], ["2025-06-05"], reference_base=base
    ).collect()

    assert len(gt) == 1
    r = gt[0]
    assert r["t_source"] == "apdf"
    assert r["aobt"] == dt.datetime(2025, 6, 5, 10, 0, 0)
    assert r["aibt"] == dt.datetime(2025, 6, 5, 11, 12, 0)
    # The ground phases the capture fractions divide by.
    assert (r["t_off"] - r["aobt"]).total_seconds() == 900
    assert (r["aibt"] - r["t_land"]).total_seconds() == 420


def test_airports_outside_the_ingestion_bbox_are_excluded(spark, tmp_path):
    """A non-European ADEP appears in NM but was never ingested.

    Its detection rate would read as zero coverage when it is really out of
    scope, and nothing in the number itself distinguishes the two.
    """
    from pyspark.sql import Row

    from oac.truth import airports_in_bbox

    p = str(tmp_path / "apts")
    spark.createDataFrame([
        Row(ident="EBBR", name="Brussels", latitude_deg=50.9, longitude_deg=4.48),
        Row(ident="KJFK", name="New York JFK", latitude_deg=40.64, longitude_deg=-73.78),
        Row(ident="OMDB", name="Dubai", latitude_deg=25.25, longitude_deg=55.36),
    ]).write.parquet(p)

    got = {r["icao"] for r in airports_in_bbox(spark, p).collect()}
    assert got == {"EBBR"}


def test_bbox_matches_osn_sample():
    """The copy in `oac.truth` must not drift from the ingestion filter.

    `oac.truth.BBOX` is a copy so that importing it does not drag in
    `osn_sample`, which opens a Spark session at import time. A copy that can
    drift is worse than an import, so the equality is asserted rather than
    assumed.
    """
    import osn_sample

    from oac.truth import BBOX

    assert BBOX == osn_sample.BBOX
