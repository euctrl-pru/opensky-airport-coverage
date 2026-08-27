"""Per-aerodrome statistics, the capture fractions and the Coverage Index.

Pure pandas throughout -- `tests/test_imports.py` asserts this path never
imports pyspark or opdi, because the site renders in GitHub Actions.
"""

import numpy as np
import pandas as pd
import pytest

from oac.aggregate import MIN_N, airport_table, by_airport, capture
from oac.rank import coverage_index, rank_tiers

T = pd.Timestamp


def _flights(n=1, **over):
    """n identical APDF flights: off-block 10:00, airborne 10:15-11:05, in 11:12.

    Taxi-out is 900 s, taxi-in 420 s. The track runs 10:05 to 11:10, so it saw
    600 s of the taxi-out and 300 s of the taxi-in.
    """
    base = dict(
        flight_key=[f"fk{i}" for i in range(n)],
        gt_adep="EBBR", gt_ades="EGLL", t_source="apdf",
        dep_measured=True, arr_measured=True,
        t_off=T("2025-06-05 10:15"), t_land=T("2025-06-05 11:05"),
        aobt=T("2025-06-05 10:00"), aibt=T("2025-06-05 11:12"),
        trk_start=T("2025-06-05 10:05"), trk_end=T("2025-06-05 11:10"),
        off_s=-600.0, land_s=300.0, match_class="clean", detected=True,
        # A fully observed ground phase by default, so every test written
        # before continuity existed keeps the meaning it had.
        dep_bins_total=30, dep_bins_seen=30, dep_max_gap_s=5.0,
        dep_n_samples=180,
        arr_bins_total=14, arr_bins_seen=14, arr_max_gap_s=5.0,
        arr_n_samples=84,
        period="2025",
    )
    base.update(over)
    return pd.DataFrame(base)


# -- capture ---------------------------------------------------------------

def test_capture_is_the_fraction_of_the_ground_phase_seen():
    out = capture(_flights())
    assert out.taxi_out_s.iloc[0] == 900
    assert out.dep_reach.iloc[0] == pytest.approx(600 / 900)
    assert out.taxi_in_s.iloc[0] == 420
    assert out.arr_reach.iloc[0] == pytest.approx(300 / 420)


def test_capture_is_clipped_to_the_unit_interval():
    """A track starting before off-block saw all of the taxi, not 140% of it."""
    out = capture(_flights(trk_start=T("2025-06-05 09:55"), off_s=-1200.0))
    assert out.dep_reach.iloc[0] == 1.0


def test_a_track_starting_after_takeoff_captures_none_of_the_ground():
    out = capture(_flights(trk_start=T("2025-06-05 10:20"), off_s=300.0))
    assert out.dep_reach.iloc[0] == 0.0


def test_non_positive_ground_phase_is_excluded_not_clipped():
    """AOBT >= ATOT is bad reference data, not zero coverage.

    Clipping would score the flight 0 or 1 and quietly move the aerodrome's
    median; excluding it and counting it is the honest option.
    """
    out = capture(_flights(aobt=T("2025-06-05 10:20")))  # off-block after take-off
    assert bool(out.capture_valid.iloc[0]) is False
    assert pd.isna(out.dep_reach.iloc[0])

    stats = by_airport(out, "dep")
    assert stats.n_capture_excluded.iloc[0] == 1
    assert pd.isna(stats.dep_reach_p50.iloc[0])


def test_an_undetected_flight_has_no_capture():
    out = capture(_flights(detected=False, off_s=np.nan, land_s=np.nan,
                           trk_start=pd.NaT, trk_end=pd.NaT))
    assert pd.isna(out.dep_reach.iloc[0])
    assert pd.isna(out.arr_reach.iloc[0])


# -- aggregation -----------------------------------------------------------

def test_detection_counts_flights_never_seen():
    df = pd.concat([
        _flights(n=3),
        _flights(n=1, detected=False, off_s=np.nan, land_s=np.nan,
                 trk_start=pd.NaT, trk_end=pd.NaT, match_class=None),
    ], ignore_index=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    stats = by_airport(capture(df), "dep")
    assert stats.n_gt.iloc[0] == 4
    assert stats.n_detected.iloc[0] == 3
    assert stats.detection_pct.iloc[0] == pytest.approx(75.0)


def test_percentiles_are_over_detected_flights_but_n_gt_counts_all():
    """The asymmetry is the point of the detection column.

    An undetected flight has no offset. Including it in a percentile would
    require inventing one; excluding it from n_gt would hide it entirely.
    """
    df = pd.concat([
        _flights(n=1, off_s=-600.0),
        _flights(n=1, detected=False, off_s=np.nan, land_s=np.nan,
                 trk_start=pd.NaT, trk_end=pd.NaT, match_class=None),
    ], ignore_index=True)
    df["flight_key"] = ["a", "b"]
    stats = by_airport(capture(df), "dep")
    assert stats.n_gt.iloc[0] == 2
    assert stats.off_s_p50.iloc[0] == pytest.approx(-600.0)


def test_departures_group_on_adep_and_arrivals_on_ades():
    df = pd.concat([
        _flights(n=2, gt_adep="EBBR", gt_ades="EGLL"),
        _flights(n=3, gt_adep="EHAM", gt_ades="EBBR"),
    ], ignore_index=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    c = capture(df)
    dep = by_airport(c, "dep").set_index("icao")
    arr = by_airport(c, "arr").set_index("icao")
    assert dep.loc["EBBR", "n_gt"] == 2
    assert dep.loc["EHAM", "n_gt"] == 3
    assert arr.loc["EGLL", "n_gt"] == 2
    assert arr.loc["EBBR", "n_gt"] == 3


def test_airport_table_keeps_an_aerodrome_with_only_one_side():
    """An outer merge, so a departure-only aerodrome keeps its row."""
    df = _flights(n=2, gt_adep="LFAA", gt_ades="EGLL")
    tbl = airport_table(df).set_index("icao")
    assert "LFAA" in tbl.index and "EGLL" in tbl.index
    assert tbl.loc["LFAA", "n_gt_dep"] == 2
    assert pd.isna(tbl.loc["LFAA", "n_gt_arr"]) or tbl.loc["LFAA", "n_gt_arr"] == 0


def test_segmentation_quality_is_reported_per_aerodrome():
    df = pd.concat([
        _flights(n=8, match_class="clean"),
        _flights(n=1, match_class="fragmented"),
        _flights(n=1, match_class="merged"),
    ], ignore_index=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    stats = by_airport(capture(df), "dep")
    assert stats.clean_pct.iloc[0] == pytest.approx(80.0)
    assert stats.fragmented_pct.iloc[0] == pytest.approx(10.0)
    assert stats.merged_pct.iloc[0] == pytest.approx(10.0)


def test_no_ground_and_full_capture_shares():
    """`no_ground` is about reach; `full_capture` is now about continuity.

    They measure different things and the fixture varies both independently.
    The first flight is never heard on the ground at all. The second spans the
    whole taxi but is observed in only half of its bins -- which under the old
    reach-based definition counted as fully captured, and no longer does.
    """
    df = pd.concat([
        # After ATOT: never on the ground, and nothing observed there.
        _flights(n=1, trk_start=T("2025-06-05 10:20"), off_s=300.0,
                 dep_bins_seen=0),
        # Spans the whole taxi, but only half its bins hold a sample.
        _flights(n=1, trk_start=T("2025-06-05 09:59"), off_s=-960.0,
                 dep_bins_seen=15),
    ], ignore_index=True)
    df["flight_key"] = ["a", "b"]
    c = capture(df)
    assert c.dep_reach.tolist() == pytest.approx([0.0, 1.0])
    assert c.dep_continuity.tolist() == pytest.approx([0.0, 0.5])

    stats = by_airport(c, "dep")
    assert stats.dep_no_ground_pct.iloc[0] == pytest.approx(50.0)
    # Neither flight clears the 0.95 continuity bar, though one has full reach.
    assert stats.dep_full_capture_pct.iloc[0] == pytest.approx(0.0)


# -- ranking ---------------------------------------------------------------

def test_coverage_index_is_detection_times_mean_capture():
    row = dict(detection_pct=80.0, dep_continuity_p50=0.5,
               arr_continuity_p50=0.9)
    assert coverage_index(row) == pytest.approx(0.8 * 0.7)


def test_coverage_index_is_null_without_capture():
    """Tier B has no capture term and must not be given a fabricated one.

    Zero would rank it below every measured aerodrome for a reason that is not
    about coverage at all.
    """
    row = dict(detection_pct=80.0, dep_continuity_p50=np.nan,
               arr_continuity_p50=np.nan)
    assert pd.isna(coverage_index(row))


def test_coverage_index_uses_the_one_capture_term_it_has():
    row = dict(detection_pct=50.0, dep_continuity_p50=0.4,
               arr_continuity_p50=np.nan)
    assert coverage_index(row) == pytest.approx(0.5 * 0.4)


def test_tiers_are_separated_and_thresholded():
    tbl = pd.DataFrame([
        dict(icao="EBBR", t_source="apdf", n_gt=500, detection_pct=90.0,
             dep_continuity_p50=0.6, arr_continuity_p50=0.8),
        dict(icao="EDDF", t_source="apdf", n_gt=400, detection_pct=95.0,
             dep_continuity_p50=0.9, arr_continuity_p50=0.9),
        dict(icao="LFXX", t_source="nm_inferred", n_gt=50, detection_pct=70.0,
             dep_continuity_p50=np.nan, arr_continuity_p50=np.nan),
        dict(icao="TINY", t_source="nm_inferred", n_gt=5, detection_pct=20.0,
             dep_continuity_p50=np.nan, arr_continuity_p50=np.nan),
    ])
    a, b = rank_tiers(tbl)
    assert list(a.icao) == ["EDDF", "EBBR"], "ranked on coverage_index, best first"
    assert list(b.icao) == ["LFXX"], f"n_gt < {MIN_N} must be cut"
    assert list(a["rank"]) == [1, 2]
    assert b["rank"].iloc[0] == 1
    assert "TINY" not in set(a.icao) | set(b.icao)


def test_tier_comes_from_the_aerodromes_own_measured_share_not_t_source():
    """Helsinki's regression, in miniature.

    An aerodrome whose own arrivals are fully measured belongs in Tier A even
    when most of its flights are labelled `nm_inferred` -- which they are
    whenever the *other* end is an aerodrome APDF does not cover. Tiering on
    the flight-level `t_source` put 26 such aerodromes in the wrong tier on the
    2025 sample, ranked on detection alone with every capture metric blank.
    """
    # Every arrival measured; every flight labelled nm_inferred because the
    # departure aerodrome is uncovered.
    df = _flights(n=10, gt_ades="EFHK", gt_adep="UUEE", t_source="nm_inferred",
                  dep_measured=False, arr_measured=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]

    tbl = airport_table(df).set_index("icao")
    assert tbl.loc["EFHK", "t_source"] == "apdf", "measured arrivals -> Tier A"
    assert tbl.loc["EFHK", "measured_pct_arr"] == pytest.approx(100.0)
    # Its arrival capture must actually be computed, not blank.
    assert not pd.isna(tbl.loc["EFHK", "arr_reach_p50"])

    # The uncovered departure aerodrome stays Tier B and has no dep capture.
    assert tbl.loc["UUEE", "t_source"] == "nm_inferred"
    assert pd.isna(tbl.loc["UUEE", "dep_reach_p50"])


def test_unmeasured_endpoints_are_not_counted_as_bad_reference_data():
    """n_capture_excluded means "measured but impossible", not "not measured"."""
    df = _flights(n=5, dep_measured=False, arr_measured=False)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    stats = by_airport(capture(df), "dep")
    assert stats.n_capture_excluded.iloc[0] == 0
    assert pd.isna(stats.dep_reach_p50.iloc[0])


def test_an_aerodrome_with_no_detected_flights_keeps_the_full_column_set():
    """The ragged-Series regression.

    `_side_stats` used to omit the no-ground and full-capture keys when an
    aerodrome had nothing detected. `groupby.apply` then received Series with
    different indexes, fell back to a positional frame with integer column
    names, and the failure surfaced far downstream as a KeyError on a column
    that existed for every other aerodrome. Every fixture in this file had
    detected flights, so nothing caught it until real data did.
    """
    seen = _flights(n=2, gt_adep="EBBR")
    unseen = _flights(n=2, gt_adep="EDDK", detected=False, off_s=np.nan,
                      land_s=np.nan, trk_start=pd.NaT, trk_end=pd.NaT,
                      match_class=None)
    df = pd.concat([seen, unseen], ignore_index=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]

    stats = by_airport(capture(df), "dep").set_index("icao")

    # Column names are strings, not positions.
    assert all(isinstance(c, str) for c in stats.columns)
    for col in ("dep_no_ground_pct", "dep_full_capture_pct", "measured_pct",
                "off_s_p50", "dep_reach_p50"):
        assert col in stats.columns

    assert stats.loc["EDDK", "n_gt"] == 2
    assert stats.loc["EDDK", "n_detected"] == 0
    assert stats.loc["EDDK", "detection_pct"] == 0.0
    assert pd.isna(stats.loc["EDDK", "dep_no_ground_pct"])
    assert pd.isna(stats.loc["EDDK", "off_s_p50"])
    # And the aerodrome that was seen is unaffected.
    assert stats.loc["EBBR", "n_detected"] == 2


def test_airport_table_survives_an_undetected_aerodrome():
    """The same case through the merge, which is where the KeyError landed."""
    df = pd.concat([
        _flights(n=2, gt_adep="EBBR", gt_ades="EGLL"),
        _flights(n=2, gt_adep="EDDK", gt_ades="EDDL", detected=False,
                 off_s=np.nan, land_s=np.nan, trk_start=pd.NaT, trk_end=pd.NaT,
                 match_class=None),
    ], ignore_index=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    tbl = airport_table(df)
    assert {"measured_pct_dep", "measured_pct_arr", "t_source"} <= set(tbl.columns)
    assert len(tbl) == 4


def test_index_ties_are_broken_by_detection():
    """Zero-capture aerodromes all score exactly 0.000, and there are many.

    Naples detects 99.7% of its movements and Gran Canaria 62%; both capture no
    ground phase at all. Ranking them equal would discard the only thing left
    that separates them.
    """
    tbl = pd.DataFrame([
        dict(icao="GCLP", t_source="apdf", n_gt=520, detection_pct=62.4,
             dep_continuity_p50=0.0, arr_continuity_p50=0.0),
        dict(icao="LIRN", t_source="apdf", n_gt=448, detection_pct=99.7,
             dep_continuity_p50=0.0, arr_continuity_p50=0.0),
    ])
    a, _ = rank_tiers(tbl)
    assert list(a.icao) == ["LIRN", "GCLP"]
    assert a.coverage_index.tolist() == [0.0, 0.0]


def test_tier_b_ties_are_broken_by_sample_size():
    tbl = pd.DataFrame([
        dict(icao="SMALL", t_source="nm_inferred", n_gt=25, detection_pct=100.0,
             dep_continuity_p50=np.nan, arr_continuity_p50=np.nan),
        dict(icao="BIG", t_source="nm_inferred", n_gt=800, detection_pct=100.0,
             dep_continuity_p50=np.nan, arr_continuity_p50=np.nan),
    ])
    _, b = rank_tiers(tbl)
    assert list(b.icao) == ["BIG", "SMALL"]


def test_airport_table_carries_the_coverage_index():
    """It is the headline number on every aerodrome page.

    Computed only in `rank_tiers`, it was absent from `airport_stats_*.csv`,
    so each page rendered its own headline as an em dash.
    """
    # Above MIN_N, so the aerodrome also reaches the ranking table below.
    df = _flights(n=25, gt_adep="EBBR", gt_ades="EGLL")
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    tbl = airport_table(df).set_index("icao")
    assert "coverage_index" in tbl.columns
    assert not pd.isna(tbl.loc["EBBR", "coverage_index"])
    # And it agrees with the ranking's own computation.
    a, _ = rank_tiers(airport_table(df))
    assert a.set_index("icao").loc["EBBR", "coverage_index"] == pytest.approx(
        tbl.loc["EBBR", "coverage_index"]
    )



# -- continuity -------------------------------------------------------------

def test_continuity_is_bins_seen_over_bins_total():
    out = capture(_flights(n=1, dep_bins_total=30, dep_bins_seen=3))
    assert out.dep_continuity.iloc[0] == pytest.approx(0.1)


def test_reach_and_continuity_disagree_on_a_single_sample():
    """The whole reason this metric exists, asserted as a contrast.

    One sample 900 s before wheels-off: reach says the taxi was covered,
    continuity says one bin in thirty was.
    """
    out = capture(_flights(n=1, off_s=-900.0, dep_bins_total=30, dep_bins_seen=1))
    assert out.dep_reach.iloc[0] == pytest.approx(1.0)
    assert out.dep_continuity.iloc[0] == pytest.approx(1 / 30)


def test_continuity_needs_a_measured_endpoint():
    out = capture(_flights(n=1, dep_measured=False))
    assert pd.isna(out.dep_continuity.iloc[0])


def test_index_uses_continuity_not_reach():
    row = dict(detection_pct=80.0, dep_continuity_p50=0.5,
               arr_continuity_p50=0.9, dep_reach_p50=1.0, arr_reach_p50=1.0)
    assert coverage_index(row) == pytest.approx(0.8 * 0.7)


def test_index_is_null_without_continuity_even_when_reach_exists():
    """Reach must never stand in for continuity.

    Falling back would silently restore the defect for exactly the aerodromes
    where continuity could not be computed.
    """
    row = dict(detection_pct=80.0, dep_continuity_p50=np.nan,
               arr_continuity_p50=np.nan, dep_reach_p50=1.0, arr_reach_p50=1.0)
    assert pd.isna(coverage_index(row))


def test_by_airport_reports_continuity_and_the_longest_gap():
    df = _flights(n=3, dep_bins_total=30, dep_bins_seen=15, dep_max_gap_s=420.0)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    stats = by_airport(capture(df), "dep")
    assert stats.dep_continuity_p50.iloc[0] == pytest.approx(0.5)
    assert stats.dep_max_gap_median_s.iloc[0] == pytest.approx(420.0)
