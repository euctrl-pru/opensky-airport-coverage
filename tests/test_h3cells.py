"""Per-aerodrome H3 cell counts: which parts of the surface are seen."""

import datetime as dt

from oac._opdi import bootstrap

bootstrap()

T = dt.datetime


def _sv(spark, rows):
    from pyspark.sql import Row

    return spark.createDataFrame([Row(**r) for r in rows])


def _sample(**over):
    row = dict(
        icao24="abc123", event_time=T(2025, 6, 5, 10, 0),
        on_ground=True, baro_altitude_c=0.0,
        lat=50.90140, lon=4.48440,
        h3_res_7="871fa4454ffffff",
    )
    row.update(over)
    return row


def _zones(spark):
    from pyspark.sql import Row

    return spark.createDataFrame([
        Row(apt_hex_id="871fa4454ffffff", apt_ident="EBBR",
            apt_max_c_radius_nm=5.0),
        Row(apt_hex_id="871fa4454ffffff", apt_ident="EBBR",
            apt_max_c_radius_nm=40.0),   # a wider band, must not double-count
    ])


def test_ground_and_low_layers_are_separated(spark):
    """An overflight at cruise must reach neither layer.

    Without the altitude filter a cruise track passing over the aerodrome
    dominates the density and drowns out the surface signal entirely -- the
    map would show the airway, not the taxiways.
    """
    from oac.h3cells import airport_cells

    sv = _sv(spark, [
        _sample(),                                            # ground
        _sample(lat=50.9060, lon=4.4900),                     # ground, other cell
        _sample(on_ground=False, baro_altitude_c=200.0),      # low (656 ft)
        _sample(on_ground=False, baro_altitude_c=10000.0),    # cruise -- excluded
    ])
    rows = airport_cells(sv, _zones(spark), res=11).collect()
    got = {}
    for r in rows:
        got[(r["icao"], r["layer"])] = got.get((r["icao"], r["layer"]), 0) + r["n"]

    assert got[("EBBR", "ground")] == 2
    assert got[("EBBR", "low")] == 1
    assert all(r["layer"] in ("ground", "low") for r in rows)


def test_positions_in_one_cell_collapse_to_a_single_row(spark):
    """Two positions metres apart share a res-11 cell and count as one row.

    Cells come from lat/lon rather than a stored index: the 2024 table has no
    `h3_res_12` at all, and mixing rollup with computation would index the
    periods differently -- which, on a map built to be compared year on year,
    would read as a change in coverage.
    """
    import h3

    from oac.h3cells import airport_cells

    lat, lon = 50.90140, 4.48440
    cell = h3.geo_to_h3(lat, lon, 11)
    # The cell's own centroid, so membership is guaranteed. A fixed metre
    # offset was tried and is flaky: two points 5 m apart straddle a boundary
    # often enough to fail, which tests the geometry rather than the rollup.
    c_lat, c_lon = h3.h3_to_geo(cell)
    sv = _sv(spark, [_sample(), _sample(lat=c_lat, lon=c_lon)])
    rows = airport_cells(sv, _zones(spark), res=11).collect()
    assert len(rows) == 1
    assert rows[0]["h3"] == cell
    assert rows[0]["n"] == 2


def test_the_raw_altitude_stands_in_when_the_cleaned_one_is_absent(spark):
    """The 2024 cleaned table carries no `baro_altitude_c`."""
    from pyspark.sql import Row

    from oac.h3cells import airport_cells

    sv = spark.createDataFrame([
        Row(icao24="a", event_time=T(2025, 6, 5, 10, 0), on_ground=False,
            baro_altitude=200.0, lat=50.9014, lon=4.4844,
            h3_res_7="871fa4454ffffff"),
        Row(icao24="a", event_time=T(2025, 6, 5, 10, 1), on_ground=False,
            baro_altitude=10000.0, lat=50.9014, lon=4.4844,
            h3_res_7="871fa4454ffffff"),
    ])
    rows = airport_cells(sv, _zones(spark), res=11).collect()
    assert sum(r["n"] for r in rows) == 1, "only the low sample survives"
    assert rows[0]["layer"] == "low"


def test_a_sample_outside_every_zone_is_dropped(spark):
    """Membership is the same 5 NM band the ranking uses, so the map and the
    numbers cannot disagree about which samples belong to an aerodrome."""
    from oac.h3cells import airport_cells

    sv = _sv(spark, [_sample(h3_res_7="87000000000ffff")])
    assert airport_cells(sv, _zones(spark), res=11).count() == 0


def test_a_zone_listed_at_several_radii_does_not_double_count(spark):
    """The zone table has one row per band; only the innermost is wanted.

    Joining without de-duplicating would multiply every sample by the number
    of bands the aerodrome has, inflating a density map by a constant factor
    that looks entirely plausible.
    """
    from oac.h3cells import airport_cells

    sv = _sv(spark, [_sample()])
    rows = airport_cells(sv, _zones(spark), res=11).collect()
    assert sum(r["n"] for r in rows) == 1
