"""Which movements become example trajectories, and how the map labels them.

The selection itself runs on the cluster (`scripts/run_examples.py` reads a
150M-row table), but the rule it applies is ordinary pandas over the committed
per-flight table. That rule is what this exercises: the cluster contributes
the geometry, not the choice.
"""

import importlib.util
import json
import re
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "oac_site_maps", REPO / "site" / "_maps.py")
_maps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_maps)

from scripts.gen_pages import _tracks_note  # noqa: E402


def _offsets():
    """Two aerodromes: one with measured times, one with NM-estimated ones.

    Both have a usable departure window; only the measured one has an arrival
    window, which is the asymmetry the selection has to honour.
    """
    rows = []
    for i in range(6):
        rows.append(dict(
            flight_key=f"m{i}", track_id=f"tm{i}", gt_adep="EBBR",
            gt_ades="EBBR", detected=True,
            dep_measured=True, arr_measured=True,
            dep_bins_seen=i, dep_bins_total=10,
            arr_bins_seen=i, arr_bins_total=10))
    for i in range(6):
        rows.append(dict(
            flight_key=f"e{i}", track_id=f"te{i}", gt_adep="LFXX",
            gt_ades="LFXX", detected=True,
            dep_measured=False, arr_measured=False,
            dep_bins_seen=i, dep_bins_total=10,
            arr_bins_seen=None, arr_bins_total=None))
    return pd.DataFrame(rows)


def _select(off, per_side=3):
    """The selection rule from `run_examples.main`, over a frame.

    Kept in step with the script by `test_the_script_still_applies_this_rule`
    below, which reads the source rather than trusting this copy.
    """
    off = off[off["detected"].fillna(False).astype(bool)]
    picks = []
    for side, key, measured, seen, total in (
        ("dep", "gt_adep", "dep_measured", "dep_bins_seen", "dep_bins_total"),
        ("arr", "gt_ades", "arr_measured", "arr_bins_seen", "arr_bins_total"),
    ):
        s = off.copy()
        if side == "arr":
            s = s[s[measured].fillna(False).astype(bool)]
        s = s[s[total].notna() & (s[total] > 0)]
        if s.empty:
            continue
        s["q"] = s[seen] / s[total]
        s["_measured"] = s[measured].fillna(False).astype(bool)
        for icao, g in s.groupby(key):
            g = g.sort_values("q")
            n = len(g)
            idx = sorted({0, n // 2, n - 1})[:per_side]
            for rank_pos, i in enumerate(idx):
                r = g.iloc[i]
                picks.append({
                    "icao": icao, "side": side, "track_id": r["track_id"],
                    "measured": bool(r["_measured"]),
                    "label": ["worst", "median", "best"][
                        min(rank_pos, 2) if len(idx) == 3
                        else (0 if rank_pos == 0 else 2)],
                })
    return pd.DataFrame(picks)


def test_an_aerodrome_without_measured_times_still_gets_departures():
    """The finding this change exists for.

    Selecting on `dep_measured` left 717 of 807 ranked aerodromes with no
    example trajectory at all -- and the map is the one place a reader sees
    *where* reception fails rather than by how much.
    """
    sel = _select(_offsets())
    lfxx = sel[sel["icao"] == "LFXX"]
    assert set(lfxx["side"]) == {"dep"}
    assert len(lfxx) == 3


def test_an_estimated_departure_is_flagged_rather_than_passed_off_as_measured():
    sel = _select(_offsets())
    assert not sel[sel["icao"] == "LFXX"]["measured"].any()
    assert sel[sel["icao"] == "EBBR"]["measured"].all()


def test_arrivals_are_never_estimated():
    """No NM in-block column exists, so an estimated arrival window cannot.

    A silently-estimated arrival would be the worst outcome here: it would
    look identical to a measured one on the map and in the ranking.
    """
    sel = _select(_offsets())
    arr = sel[sel["side"] == "arr"]
    assert len(arr) and arr["measured"].all()
    assert set(arr["icao"]) == {"EBBR"}


def test_a_measured_aerodrome_keeps_both_sides():
    sel = _select(_offsets())
    assert set(sel[sel["icao"] == "EBBR"]["side"]) == {"dep", "arr"}


def test_the_script_still_applies_this_rule():
    """Guards the copy above against the script drifting away from it.

    The selection cannot be imported -- `run_examples` calls `bootstrap()` and
    builds a Spark session at import time -- so the rule is duplicated here.
    A duplicated rule that nothing checks is one that silently diverges.
    """
    src = (REPO / "scripts" / "run_examples.py").read_text()
    assert 'if side == "arr":' in src
    assert 's = s[s[measured].fillna(False).astype(bool)]' in src
    assert '"measured": bool(r["_measured"])' in src


# --- how the map presents them -------------------------------------------

def _tracks(measured):
    return pd.DataFrame({
        "track_id": ["t1"] * 3, "label": ["best"] * 3,
        "lat": [50.90, 50.91, 50.92], "lon": [4.48, 4.49, 4.50],
        "event_time": pd.to_datetime(["2026-06-05 08:00:00",
                                      "2026-06-05 08:00:05",
                                      "2026-06-05 08:00:10"]),
        "side": ["dep"] * 3, "measured": [measured] * 3,
    })


def _names(html):
    m = re.search(r'Plotly\.newPlot\(\s*"[^"]+",\s*(\[.*?\]),\s*\{', html, re.S)
    return [t.get("name") for t in json.loads(m.group(1))]


def test_the_legend_says_when_a_flight_is_ranked_against_an_estimate():
    cells = pd.DataFrame(columns=["h3", "layer", "n"])
    names = _names(_maps.coverage_map(cells, _tracks(False)))
    assert any("est. window" in n for n in names)


def test_the_legend_stays_clean_for_a_measured_flight():
    cells = pd.DataFrame(columns=["h3", "layer", "n"])
    names = _names(_maps.coverage_map(cells, _tracks(True)))
    assert not any("est. window" in n for n in names)


def test_an_extraction_without_the_flag_is_treated_as_measured():
    """The committed parquet pre-dates the column; it must still draw.

    Before the flag existed the selection took measured movements only, so
    absence means measured -- and a KeyError here would take out every
    aerodrome page at once.
    """
    cells = pd.DataFrame(columns=["h3", "layer", "n"])
    t = _tracks(True).drop(columns=["measured"])
    names = _names(_maps.coverage_map(cells, t))
    assert names and not any("est. window" in n for n in names)


# --- the note beneath the map --------------------------------------------

def test_no_examples_at_all_says_so():
    assert "No movement here has one" in _tracks_note(pd.DataFrame())


def test_all_measured_needs_no_caveat():
    assert _tracks_note(_tracks(True)) is None


def test_all_estimated_explains_the_missing_arrivals():
    note = _tracks_note(_tracks(False))
    assert "predicted taxi duration" in note
    assert "no in-block column" in note


def test_a_mixed_aerodrome_points_at_the_marked_flights():
    mixed = pd.concat([_tracks(True), _tracks(False)], ignore_index=True)
    note = _tracks_note(mixed)
    assert "est. window" in note


@pytest.mark.parametrize("measured", [True, False])
def test_every_shape_still_produces_a_map(measured):
    cells = pd.DataFrame(columns=["h3", "layer", "n"])
    assert _maps.coverage_map(cells, _tracks(measured))
