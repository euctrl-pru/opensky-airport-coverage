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
        period="2025",
    )
    base.update(over)
    return pd.DataFrame(base)


# -- capture ---------------------------------------------------------------

def test_capture_is_the_fraction_of_the_ground_phase_seen():
    out = capture(_flights())
    assert out.taxi_out_s.iloc[0] == 900
    assert out.dep_capture.iloc[0] == pytest.approx(600 / 900)
    assert out.taxi_in_s.iloc[0] == 420
    assert out.arr_capture.iloc[0] == pytest.approx(300 / 420)


def test_capture_is_clipped_to_the_unit_interval():
    """A track starting before off-block saw all of the taxi, not 140% of it."""
    out = capture(_flights(trk_start=T("2025-06-05 09:55"), off_s=-1200.0))
    assert out.dep_capture.iloc[0] == 1.0


def test_a_track_starting_after_takeoff_captures_none_of_the_ground():
    out = capture(_flights(trk_start=T("2025-06-05 10:20"), off_s=300.0))
    assert out.dep_capture.iloc[0] == 0.0


def test_non_positive_ground_phase_is_excluded_not_clipped():
    """AOBT >= ATOT is bad reference data, not zero coverage.

    Clipping would score the flight 0 or 1 and quietly move the aerodrome's
    median; excluding it and counting it is the honest option.
    """
    out = capture(_flights(aobt=T("2025-06-05 10:20")))  # off-block after take-off
    assert bool(out.capture_valid.iloc[0]) is False
    assert pd.isna(out.dep_capture.iloc[0])

    stats = by_airport(out, "dep")
    assert stats.n_capture_excluded.iloc[0] == 1
    assert pd.isna(stats.dep_capture_p50.iloc[0])


def test_an_undetected_flight_has_no_capture():
    out = capture(_flights(detected=False, off_s=np.nan, land_s=np.nan,
                           trk_start=pd.NaT, trk_end=pd.NaT))
    assert pd.isna(out.dep_capture.iloc[0])
    assert pd.isna(out.arr_capture.iloc[0])


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
    df = pd.concat([
        _flights(n=1, trk_start=T("2025-06-05 10:20"), off_s=300.0),   # after ATOT
        _flights(n=1, trk_start=T("2025-06-05 09:59"), off_s=-960.0),  # full taxi
    ], ignore_index=True)
    df["flight_key"] = ["a", "b"]
    stats = by_airport(capture(df), "dep")
    assert stats.dep_no_ground_pct.iloc[0] == pytest.approx(50.0)
    assert stats.dep_full_capture_pct.iloc[0] == pytest.approx(50.0)


# -- ranking ---------------------------------------------------------------

def test_coverage_index_is_detection_times_mean_capture():
    row = dict(detection_pct=80.0, dep_capture_p50=0.5, arr_capture_p50=0.9)
    assert coverage_index(row) == pytest.approx(0.8 * 0.7)


def test_coverage_index_is_null_without_capture():
    """Tier B has no capture term and must not be given a fabricated one.

    Zero would rank it below every measured aerodrome for a reason that is not
    about coverage at all.
    """
    row = dict(detection_pct=80.0, dep_capture_p50=np.nan, arr_capture_p50=np.nan)
    assert pd.isna(coverage_index(row))


def test_coverage_index_uses_the_one_capture_term_it_has():
    row = dict(detection_pct=50.0, dep_capture_p50=0.4, arr_capture_p50=np.nan)
    assert coverage_index(row) == pytest.approx(0.5 * 0.4)


def test_tiers_are_separated_and_thresholded():
    tbl = pd.DataFrame([
        dict(icao="EBBR", t_source="apdf", n_gt=500, detection_pct=90.0,
             dep_capture_p50=0.6, arr_capture_p50=0.8),
        dict(icao="EDDF", t_source="apdf", n_gt=400, detection_pct=95.0,
             dep_capture_p50=0.9, arr_capture_p50=0.9),
        dict(icao="LFXX", t_source="nm_inferred", n_gt=50, detection_pct=70.0,
             dep_capture_p50=np.nan, arr_capture_p50=np.nan),
        dict(icao="TINY", t_source="nm_inferred", n_gt=5, detection_pct=20.0,
             dep_capture_p50=np.nan, arr_capture_p50=np.nan),
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
    assert not pd.isna(tbl.loc["EFHK", "arr_capture_p50"])

    # The uncovered departure aerodrome stays Tier B and has no dep capture.
    assert tbl.loc["UUEE", "t_source"] == "nm_inferred"
    assert pd.isna(tbl.loc["UUEE", "dep_capture_p50"])


def test_unmeasured_endpoints_are_not_counted_as_bad_reference_data():
    """n_capture_excluded means "measured but impossible", not "not measured"."""
    df = _flights(n=5, dep_measured=False, arr_measured=False)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    stats = by_airport(capture(df), "dep")
    assert stats.n_capture_excluded.iloc[0] == 0
    assert pd.isna(stats.dep_capture_p50.iloc[0])
