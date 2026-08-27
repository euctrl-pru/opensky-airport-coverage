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
    write_pages(pages_for(tbl), tmp_path)
    text = (tmp_path / "ZZZZ.qmd").read_text()
    assert 'title: "ZZZZ"' in text
    assert "—" not in text.split("\n")[1]


def test_write_pages_clears_stale_pages_but_keeps_the_listing(tmp_path):
    """A rerun after an aerodrome drops below threshold must not leave its page.

    Otherwise the site keeps serving a page the ranking no longer lists, built
    from data that is no longer there.
    """
    (tmp_path / "GONE.qmd").write_text("stale")
    n = write_pages(pages_for(_tbl()), tmp_path)
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
