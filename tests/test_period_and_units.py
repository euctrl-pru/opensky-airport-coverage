"""A movement count needs its period, and a duration needs its unit.

Both are the same class of defect: a number whose label does not say what it
is. "Movements: 516" reads as a total when it is three sampled days of one
June, and a column headed "(min, median)" carrying 225 is simply wrong.
"""

from pathlib import Path

import pandas as pd
import pytest

from oac.labels import (PERIOD_SCOPED, SAMPLE_DAYS, label, rename, tip_header,
                        tip_headers)
from oac.page import SEC_PER_MIN
from oac.tables import all_aerodromes_table
from scripts.gen_pages import pages_for

REPO = Path(__file__).resolve().parent.parent


# --- the period on movement counts ---------------------------------------

def test_a_movement_count_names_its_period_and_the_sample_length():
    """516 movements is three sampled days, not a June total."""
    assert label("n_movements", "2026") == "Movements 2026 sample (3 days)"
    assert label("n_detected", "2026") == "Movements seen 2026 sample (3 days)"


def test_columns_that_are_not_counts_are_left_alone():
    """Adding the period everywhere would put (2026) on ICAO and on the rank."""
    for col in ("icao", "rank", "coverage_index", "detection_pct"):
        assert label(col, "2026") == label(col), col
        assert "2026" not in label(col, "2026")


def test_no_period_leaves_every_label_unchanged():
    """The downloads and any caller without a period keep the old headers."""
    for col in list(PERIOD_SCOPED) + ["icao", "coverage_index"]:
        assert label(col, None) == label(col)


def test_the_period_reaches_both_header_paths():
    df = pd.DataFrame({"n_movements": [1], "icao": ["EBBR"]})
    want = "Movements 2026 sample (3 days)"
    assert want in rename(df, "2026").columns
    assert any(want in c for c in tip_headers(df, "2026").columns)


def test_a_tooltip_header_still_carries_its_tooltip():
    """The period must not displace the tooltip markup that wraps the name."""
    h = tip_header("n_movements", "2026")
    assert "Movements 2026 sample (3 days)" in h
    assert "data-bs-toggle" in h


def test_the_stated_sample_length_matches_the_committed_data():
    """The header asserts three days; the extracts must actually hold three.

    Without this the label is a hardcoded claim that goes stale silently the
    first time the sample changes -- and it is the number a reader uses to
    decide whether 516 movements is a lot.
    """
    import glob

    found = sorted(glob.glob(str(REPO / "data" / "flight_offsets_*.parquet")))
    if not found:
        pytest.skip("no committed extracts")
    for path in found:
        d = pd.read_parquet(path, columns=["aobt", "t_off"])
        days = pd.concat([d["aobt"], d["t_off"]]).dropna().dt.date.nunique()
        # A flight can straddle midnight, so a 3-day sample touches at most 4
        # calendar dates. The claim under test is the sample length, not the
        # count of dates any timestamp falls on.
        assert SAMPLE_DAYS <= days <= SAMPLE_DAYS + 1, (
            f"{Path(path).name}: {days} distinct dates, "
            f"label claims {SAMPLE_DAYS} sampled days")


def test_an_aerodrome_page_header_names_the_period():
    tbl = pd.DataFrame([dict(icao="EBBR", name="Brussels", t_source="apdf",
                             n_gt=843)])
    page = list(pages_for(tbl, "2026"))[0]
    assert "843 movements in 2026" in page.header


def test_a_page_built_without_a_period_does_not_invent_one():
    tbl = pd.DataFrame([dict(icao="EBBR", name="Brussels", t_source="apdf",
                             n_gt=843)])
    page = list(pages_for(tbl))[0]
    assert "843 movements" in page.header
    assert " in " not in page.header.split("·")[1]


def test_the_storyline_names_the_period():
    from oac.page import _storyline

    row = pd.Series({"detection_pct_dep": 99.9, "coverage_index": 0.8,
                     "dep_signal_p50": 0.7})
    assert "in 2026" in _storyline("A", row, "2026")


# --- the unit on ranking durations ---------------------------------------

def _ranking_row(**over):
    row = dict(rank=1, icao="EBBR", name="Brussels", n_gt=843,
               n_gt_dep=843, n_gt_arr=802,
               detection_pct=99.8, measured="yes",
               off_s_p50=-725.0, land_s_p50=375.0, dep_signal_p50=0.764)
    row.update(over)
    return pd.DataFrame([row])


def test_ranking_durations_are_minutes_not_seconds():
    """The bug this test exists for: the label said min, the value was 225.

    `labels.py` moved these columns to "(min, median)" when the site went to
    minutes, but `all_aerodromes_table` kept rounding raw seconds -- so the
    ranking showed seconds under a minutes heading.
    """
    t = all_aerodromes_table(_ranking_row())
    assert t["off_s_p50"].iloc[0] == pytest.approx(-725.0 / SEC_PER_MIN, abs=0.05)
    assert t["land_s_p50"].iloc[0] == pytest.approx(375.0 / SEC_PER_MIN, abs=0.05)


def test_the_label_and_the_value_agree_on_the_unit():
    t = all_aerodromes_table(_ranking_row())
    assert "(min" in label("off_s_p50")
    # A value still in seconds would be ~60x this.
    assert abs(t["off_s_p50"].iloc[0]) < 60


def test_a_missing_duration_stays_missing():
    t = all_aerodromes_table(_ranking_row(off_s_p50=None))
    assert pd.isna(t["off_s_p50"].iloc[0])


# --- movements is both sides, not the larger one -------------------------

def test_movements_counts_take_offs_plus_landings():
    """The defect: Istanbul showed 2,132 for an aerodrome that saw 4,262.

    `n_gt` is `max(dep, arr)` -- correct as the ranking floor, wrong under a
    column headed "Movements", which in aviation means both.
    """
    from oac.tables import with_movements

    t = with_movements(_ranking_row())
    assert t["n_movements"].iloc[0] == 843 + 802


def test_the_ranking_floor_still_uses_the_larger_side():
    """Switching the gate to the sum would admit 434 aerodromes, not 352.

    That is a separate decision from fixing the label, and this pins that it
    was not made by accident.
    """
    from oac.tables import with_movements

    t = with_movements(_ranking_row())
    assert t["n_gt"].iloc[0] == 843


def test_one_known_side_still_gives_a_count():
    """27 aerodromes have no recorded arrivals, 34 no departures."""
    from oac.tables import with_movements

    t = with_movements(_ranking_row(n_gt_arr=None))
    assert t["n_movements"].iloc[0] == 843


def test_a_frame_without_the_side_columns_does_not_raise():
    """`DataFrame.get` returns None for a missing column, not an empty Series."""
    from oac.tables import with_movements

    t = with_movements(pd.DataFrame({"icao": ["EBBR"], "n_gt": [843]}))
    assert t["n_movements"].iloc[0] == 0


def test_the_ranking_table_shows_the_total():
    t = all_aerodromes_table(_ranking_row())
    assert "n_movements" in t.columns and "n_gt" not in t.columns
    assert t["n_movements"].iloc[0] == 1645


def test_an_aerodrome_page_header_shows_the_total():
    tbl = pd.DataFrame([dict(icao="EBBR", name="Brussels", t_source="apdf",
                             n_gt=843, n_gt_dep=843, n_gt_arr=802)])
    page = list(pages_for(tbl, "2026"))[0]
    assert "1,645 movements in 2026" in page.header
    assert page.n_gt == 843, "the ranking floor must stay on the larger side"
