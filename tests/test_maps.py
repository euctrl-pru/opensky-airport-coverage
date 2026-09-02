"""What an aerodrome's coverage map opens on.

The map has two layers and they are not always both present. 235 of the ranked
aerodromes have no ground layer at all -- nothing whatever is received while
aircraft are on the surface -- and for those the airborne layer is the only
thing there is to draw.
"""

import importlib.util
import json
import re
from pathlib import Path

import h3
import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

# `site/` cannot be imported as a package -- `site` is a stdlib module, and
# `pythonpath` puts the repo root on the path, so `import site._maps` resolves
# to the interpreter's own. Loading the file directly is what `test_imports`
# does through a subprocess, without needing one.
_spec = importlib.util.spec_from_file_location(
    "oac_site_maps", Path(__file__).resolve().parent.parent / "site" / "_maps.py")
_maps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_maps)


def _cells(layers):
    """One cell per named layer, all near the same point."""
    to_cell = getattr(h3, "latlng_to_cell", None) or h3.geo_to_h3
    rows = []
    for i, layer in enumerate(layers):
        rows.append({"h3": to_cell(50.9 + i * 0.001, 4.48, 11),
                     "layer": layer, "n": 100 + i})
    return pd.DataFrame(rows)


def _traces(html):
    """The plotly traces embedded in the returned fragment.

    The fragment is a script tag carrying one JSON payload; parsing it is what
    lets the test assert on what the reader's browser will actually draw
    rather than on a substring that could appear in a comment or a hovertext.
    """
    m = re.search(r'Plotly\.newPlot\(\s*"[^"]+",\s*(\[.*?\]),\s*\{', html,
                  re.S)
    assert m, "no Plotly.newPlot payload in the fragment"
    return json.loads(m.group(1))


def _by_name(html):
    return {t.get("name"): t for t in _traces(html) if "name" in t}


def test_the_airborne_layer_is_hidden_when_there_is_ground_to_hide():
    """The established behaviour, kept: airborne over ground obscures it.

    The airborne layer covers roughly ten times the area, so drawn on top it
    buries the taxiway-level detail the map exists for.
    """
    html = _maps.coverage_map(_cells(["ground", "low"]))
    traces = _by_name(html)
    assert traces["On the ground"]["visible"] is True
    assert traces["Airborne below 1,500 ft"]["visible"] == "legendonly"


def test_the_airborne_layer_is_shown_when_it_is_the_only_layer():
    """With no ground layer, hiding the airborne one leaves an empty map.

    This is the LTFM case. Istanbul has 429 airborne cells and not one ground
    cell, and every one of them started hidden -- so the page opened on a bare
    basemap, which reads as "no data for this aerodrome" when the finding is
    the sharper one that reception never reaches the surface.
    """
    html = _maps.coverage_map(_cells(["low"]))
    traces = _by_name(html)
    assert "On the ground" not in traces
    assert traces["Airborne below 1,500 ft"]["visible"] is True


def test_a_ground_only_aerodrome_still_shows_its_ground_layer():
    html = _maps.coverage_map(_cells(["ground"]))
    assert _by_name(html)["On the ground"]["visible"] is True


def test_nothing_at_all_draws_no_map():
    """An empty frame is not an empty map -- it is no map.

    The caller distinguishes the two, and a figure with no traces would be
    rendered as a blank basemap that asserts coverage was measured here.
    """
    empty = pd.DataFrame(columns=["h3", "layer", "n"])
    assert _maps.coverage_map(empty) is None


@pytest.mark.parametrize("layers", [["ground", "low"], ["low"]])
def test_both_shapes_render_a_usable_fragment(layers):
    html = _maps.coverage_map(_cells(layers))
    assert html and "Plotly.newPlot" in html


# --- the prose that sits above the map -----------------------------------

def _section(has_ground):
    """The rendered `## Where the coverage is` section for one flag."""
    from oac.page import _map_section

    return _map_section({"map_html": "<div>m</div>",
                         "map_has_ground": has_ground})


def test_the_map_prose_offers_the_airborne_layer_when_it_is_hidden():
    assert "add the **airborne** layer" in _section(True)


def test_the_map_prose_states_the_finding_when_no_ground_is_received():
    """With no ground layer the reader needs the finding, not an instruction.

    "Use the legend to add the airborne layer" names a control that will not
    change anything here, and it leaves the actual result -- that reception
    never reaches the surface -- to be inferred from an absence.
    """
    body = _section(False)
    assert "Nothing here was received on the ground" in body
    assert "add the **airborne** layer" not in body


def test_both_branches_still_embed_the_map():
    for flag in (True, False):
        assert "<div>m</div>" in _section(flag)
