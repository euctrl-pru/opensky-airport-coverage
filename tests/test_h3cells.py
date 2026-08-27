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
        h3_res_7="871fa4454ffffff", h3_res_12="8c1fa445406a1ff",
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
        _sample(h3_res_12="8c1fa445406a3ff"),                 # ground, other cell
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


def test_cells_are_rolled_up_to_the_requested_resolution(spark):
    """Two res-12 cells inside one res-11 parent collapse to a single row."""
    import h3

    from oac.h3cells import airport_cells

    child_a = "8c1fa445406a1ff"
    parent = h3.h3_to_parent(child_a, 11)
    child_b = [c for c in h3.h3_to_children(parent, 12) if c != child_a][0]

    sv = _sv(spark, [_sample(h3_res_12=child_a), _sample(h3_res_12=child_b)])
    rows = airport_cells(sv, _zones(spark), res=11).collect()
    assert len(rows) == 1
    assert rows[0]["h3"] == parent
    assert rows[0]["n"] == 2


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
