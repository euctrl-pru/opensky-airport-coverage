"""A movement count needs its period, and a duration needs its unit.

Both are the same class of defect: a number whose label does not say what it
is. "Movements: 516" reads as a total when it is three sampled days of one
June, and a column headed "(min, median)" carrying 225 is simply wrong.
"""

import pandas as pd
import pytest

from oac.labels import PERIOD_SCOPED, label, rename, tip_header, tip_headers
from oac.page import SEC_PER_MIN
from oac.tables import all_aerodromes_table
from scripts.gen_pages import Page, pages_for


# --- the period on movement counts ---------------------------------------

def test_a_movement_count_carries_its_period():
    assert label("n_gt", "2026") == "Movements (2026)"
    assert label("n_detected", "2026") == "Movements seen (2026)"


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
    df = pd.DataFrame({"n_gt": [1], "icao": ["EBBR"]})
    assert "Movements (2026)" in rename(df, "2026").columns
    assert any("Movements (2026)" in c for c in tip_headers(df, "2026").columns)


def test_a_tooltip_header_still_carries_its_tooltip():
    """The period must not displace the tooltip markup that wraps the name."""
    h = tip_header("n_gt", "2026")
    assert "Movements (2026)" in h
    assert "data-bs-toggle" in h


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
