import pandas as pd

from scripts.gen_pages import Page, pages_for, write_pages


def _tbl():
    return pd.DataFrame([
        dict(icao="EBBR", name="Brussels", t_source="apdf", n_gt=500),
        dict(icao="LFXX", name="Small", t_source="nm_inferred", n_gt=50),
        dict(icao="TINY", name="Tiny", t_source="nm_inferred", n_gt=5),
    ])


def test_one_page_per_qualifying_aerodrome_and_none_below_threshold():
    """An aerodrome below MIN_N gets no page at all.

    A per-aerodrome percentile over single-digit movements is noise wearing the
    same formatting as a finding.
    """
    assert {p.icao for p in pages_for(_tbl())} == {"EBBR", "LFXX"}


def test_tier_is_carried_into_the_page_header_not_a_footnote():
    page = [p for p in pages_for(_tbl()) if p.icao == "LFXX"][0]
    assert page.tier == "B"
    assert "NM-inferred" in page.header
    assert "no capture" in page.header


def test_tier_a_header_says_milestones_are_measured():
    page = [p for p in pages_for(_tbl()) if p.icao == "EBBR"][0]
    assert page.tier == "A"
    assert "measured" in page.header


def test_a_missing_name_does_not_produce_a_dangling_dash(tmp_path):
    tbl = pd.DataFrame([dict(icao="ZZZZ", name=None, t_source="apdf", n_gt=99)])
    write_pages(pages_for(tbl), tmp_path, slices=tmp_path / "none")
    text = (tmp_path / "ZZZZ.qmd").read_text()
    assert 'title: "ZZZZ"' in text
    assert "—" not in text.split("\n")[1]


def test_write_pages_clears_stale_pages_but_keeps_the_listing(tmp_path):
    """A rerun after an aerodrome drops below threshold must not leave its page.

    Otherwise the site keeps serving a page the ranking no longer lists, built
    from data that is no longer there.
    """
    (tmp_path / "GONE.qmd").write_text("stale")
    n = write_pages(pages_for(_tbl()), tmp_path, slices=tmp_path / "none")
    assert n == 2
    assert not (tmp_path / "GONE.qmd").exists()
    assert (tmp_path / "EBBR.qmd").exists()
    listing = (tmp_path / "index.qmd").read_text()
    assert "EBBR" in listing and "LFXX" in listing and "TINY" not in listing


def test_generated_page_calls_the_shared_renderer():
    """The page must stay three lines; layout lives in _airport.py."""
    tbl = pd.DataFrame([dict(icao="EDDF", name="Frankfurt",
                             t_source="apdf", n_gt=800)])
    pg = list(pages_for(tbl))[0]
    assert isinstance(pg, Page)


def test_a_name_containing_quotes_produces_valid_yaml(tmp_path):
    """Rhodes is literally `Rhodes International Airport "Diagoras"`.

    Its embedded quotes ended the YAML title early and failed the *whole*
    project render -- 424 pages -- with an error naming a line in a generated
    file. Aerodrome names are free text from OurAirports; the front matter must
    survive whatever is in them.
    """
    import yaml

    tbl = pd.DataFrame([
        dict(icao="LGRP", name='Rhodes International Airport "Diagoras"',
             t_source="nm_inferred", n_gt=346),
        dict(icao="WEIRD", name="A|B: c #d 'e'", t_source="apdf", n_gt=99),
    ])
    write_pages(pages_for(tbl), tmp_path, slices=tmp_path / "none")

    for icao in ("LGRP", "WEIRD"):
        text = (tmp_path / f"{icao}.qmd").read_text()
        front = text.split("---")[1]
        meta = yaml.safe_load(front)
        assert icao in meta["title"]
        assert isinstance(meta["subtitle"], str)

    # And the listing table's cells are not broken by a pipe in a name.
    listing = (tmp_path / "index.qmd").read_text()
    assert r"A\|B" in listing


def test_airport_pages_contain_no_executable_cells():
    """The 424 aerodrome pages must be pure markdown.

    Quarto's `execute: daemon` reuses a kernel across re-renders of *one* file,
    not across many, so every executable page pays a fresh Python kernel --
    about 10 s each, over an hour for this site, nearly all of it startup. The
    figures and tables are built once in `gen_pages.py`, where the data is
    already in memory.
    """
    import re
    from pathlib import Path

    site = Path(__file__).resolve().parent.parent / "site" / "airports"
    pages = [p for p in site.glob("*.qmd") if p.name != "index.qmd"]
    if not pages:
        return  # nothing generated yet; scripts/gen_pages.py has not run
    for page in pages[:25]:
        text = page.read_text()
        assert not re.search(r"^```\{python", text, re.M), (
            f"{page.name} carries an executable cell"
        )


def test_every_figure_is_closed_after_display():
    """Leaked figures degrade the whole render, not just one page.

    `execute: daemon: true` keeps one kernel for all 429 pages, so a figure a
    page leaves open stays open for every page after it. Unclosed, the render
    started at ~7 s/page and had degraded past 100 s by page twelve -- on its
    way to a CI timeout that would have read as "Quarto is slow".

    Asserted structurally because the symptom is a slowdown, not a failure:
    nothing errors, and a wall-clock test would be flaky. `gen_pages.py` draws
    hundreds of figures in one process and is checked separately.
    """
    from pathlib import Path

    site = Path(__file__).resolve().parent.parent / "site"
    for name in ("index.qmd",):
        text = (site / name).read_text()
        shown = text.count("display(fig)")
        closed = text.count("plt.close(fig)") + text.count("_show(fig)")
        assert closed >= shown, (
            f"{name}: {shown} display(fig) but only {closed} closed. "
            "Every figure must be closed or the daemon kernel accumulates them."
        )


def test_a_chart_with_no_series_returns_no_figure():
    """A blank axis reads as "no coverage", which is a different claim.

    An aerodrome with no detected movements on one side produced an
    axis-only chart with an empty legend box, plus a matplotlib UserWarning.
    Returning None lets the page omit the figure instead.
    """
    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
    import _charts

    fig, overflow = _charts.signed_histogram({"2025": np.array([])})
    assert fig is None
    assert overflow == {"2025": (0, 0)}

    fig, _ = _charts.signed_histogram({"2025": np.random.normal(0, 300, 200)})
    assert fig is not None


def test_no_hour_of_day_figure_is_generated():
    """Removed 2026-08-29: two figures per page carrying no usable signal.

    They plotted the median boundary offset against hour of day for up to 704
    SVGs a build. Asserted rather than simply deleted, because the block is
    easy to reinstate by copying an adjacent one.
    """
    # `_charts` lives under `site/`, not on the package path, so it is
    # imported inside the test -- the same way the neighbouring figure tests
    # in this file do it. Do not hoist this to module level.
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "site"))
    import _charts

    assert not hasattr(_charts, "by_hour"), (
        "_charts.by_hour is back; the hour-of-day figures were removed"
    )
    src = (repo / "scripts" / "gen_pages.py").read_text()
    assert "_hour" not in src, "gen_pages still emits an hour-of-day figure"
    page_src = (repo / "src" / "oac" / "page.py").read_text()
    assert "_hour" not in page_src, "page.py still renders an hour-of-day figure"


def test_an_aerodrome_with_no_cells_still_gets_an_explanation():
    """Absence of a map is the strongest coverage statement it can make.

    Naples has 4,563 position reports inside its zone across three days --
    every one airborne, not one below 1,500 ft. An earlier version returned an
    empty string, so the page where that finding matters most said nothing.
    """
    from oac.page import _map_section

    assert _map_section({"maps": {}, "map_expected": True}).count("Nothing observed") == 1
    # But when no H3 data exists at all, silence is right: that is a statement
    # about the pipeline, not about the aerodrome.
    assert _map_section({"maps": {}}) == ""
    assert _map_section({}) == ""


def test_no_module_defines_the_same_function_twice():
    """A duplicated def silently shadows the earlier one.

    A slice-based edit to `oac/page.py` once inserted a new `_map_section`
    without removing the old one, and Python took the last definition -- so the
    new interactive map was built, discarded, and every page reported that
    nothing had been observed. Nothing failed; the output was simply wrong.
    """
    import ast
    from collections import Counter
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for py in list((root / "src" / "oac").glob("*.py")) + \
            list((root / "site").glob("*.py")) + \
            list((root / "scripts").glob("*.py")):
        tree = ast.parse(py.read_text())
        names = Counter(
            n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        dupes = [n for n, c in names.items() if c > 1]
        assert not dupes, f"{py.name} defines {dupes} more than once"


def test_an_aerodrome_in_both_ranking_tables_gets_one_page():
    """The all-aerodromes ranking includes the measured ones by design.

    Concatenating the two files therefore lists those aerodromes twice, which
    generated their pages twice and reported 138 measured aerodromes where
    there are 69. The measured row must be the survivor: it carries the
    ground-coverage columns the page needs.
    """
    import pandas as pd
    from scripts.gen_pages import _dedupe_rankings

    both = pd.DataFrame([
        dict(icao="EBBR", t_source="apdf", n_gt=843, dep_signal_p50=1.0),
        dict(icao="EBBR", t_source="apdf", n_gt=843, dep_signal_p50=1.0),
        dict(icao="LFXX", t_source="nm_inferred", n_gt=50,
             dep_signal_p50=float("nan")),
    ])
    out = _dedupe_rankings(both)
    assert list(out.icao) == ["EBBR", "LFXX"]
    assert out[out.icao == "EBBR"].t_source.iloc[0] == "apdf"
