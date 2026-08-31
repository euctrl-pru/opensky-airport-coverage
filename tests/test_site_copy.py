"""Guards on what the site's pages actually say.

The `.qmd` files carry the framing prose and decide which columns reach a
table. Nothing else in the suite reads them, so an editorial decision -- which
measures lead, which are dropped as redundant -- can be reverted by a one-line
edit with no test objecting. These read the pages as text; they do not render
them, so they need neither Quarto nor a kernel.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "site" / "index.qmd"


def chunk_source() -> str:
    """Every `{python}` chunk in index.qmd, concatenated."""
    text = INDEX.read_text()
    return "\n".join(re.findall(r"```\{python\}(.*?)```", text, re.S))


def test_the_page_builds_its_tables_from_the_shared_module():
    """The page and its downloads must be one composition, not two.

    `signal_p50` was removed from the ranking (r = 0.998 against
    `coverage_index`, same rating band for 86 of 89) and detection was demoted
    but kept. Those column-level guarantees are asserted behaviourally in
    `tests/test_tables.py`, against the frame the builder returns -- grepping
    this page for a column name passes as happily on a comment as on code.

    What is asserted *here* is the property only the page can violate: that it
    calls the shared builders instead of composing the tables inline again. An
    inline rebuild is how the download comes to disagree with the table above
    it, which is the whole reason the composition was extracted.
    """
    src = chunk_source()
    assert "measured_table(a)" in src, (
        "the measured ranking is not built by oac.tables.measured_table"
    )
    assert "all_aerodromes_table(b)" in src, (
        "the all-aerodromes ranking is not built by oac.tables.all_aerodromes_table"
    )
    assert 't["tracking_err_pct"] = ' not in src, (
        "the page is composing a ranking column inline again; that column "
        "belongs to oac.tables, or the download will not carry it"
    )


def test_the_coverage_index_formula_is_explained_where_it_is_used():
    """The formula was printed as bare identifiers with no gloss.

    A reader met `detection_rate x mean(dep_signal_p50, arr_signal_p50)` with
    nothing on the page saying what any of the three are. That gloss has
    since moved off the rankings page onto column tooltips and the Metrics
    page (tooltips point there) -- so what this test can still hold is that
    the terms are defined *somewhere* the page links to, not that they are
    spelled out inline.
    """
    text = INDEX.read_text()
    assert "## Ground coverage" in text, (
        "heading '## Ground coverage' moved or was renamed; update this test"
    )
    assert "## Flights seen" in text, (
        "heading '## Flights seen' moved or was renamed; update this test"
    )
    intro = text[text.index("## Ground coverage"):text.index("## Flights seen")]
    assert "coverage index" in intro.lower(), (
        "the ground-coverage intro no longer names the coverage index"
    )
    assert "metrics.qmd" in text, (
        "the page no longer links to the Metrics page for the full formula"
    )
    metrics = (REPO / "site" / "metrics.qmd").read_text().lower()
    for phrase in ("seen at all", "taxi-out", "taxi-in", "median"):
        assert phrase in metrics, (
            f"the formula gloss for {phrase!r} is missing from metrics.qmd"
        )


def test_ground_coverage_leads_the_fleet_summary():
    """Detection is 99.7% almost everywhere and teaches the reader nothing.

    It stays -- it is the only measure the estimated aerodromes can be ranked
    on, and its fleet minimum of 76% is real -- but it stops going first. The
    site is about the ground portion, so the ground rows lead.
    """
    src = chunk_source()
    taxi = src.index('"Taxi-out received')
    seen = src.index('"Flights seen')
    assert taxi < seen, (
        "the fleet summary still opens with two detection rows; the ground "
        "measures should come first"
    )


def test_the_coverage_section_leads_with_the_ground_question():
    """"Was the flight seen at all?" was the first of the two questions."""
    text = INDEX.read_text()
    assert '## What "coverage" means here' in text, (
        'heading \'## What "coverage" means here\' moved or was renamed; '
        "update this test"
    )
    section = text[text.index('## What "coverage" means here'):]
    ground = section.index("How much of its time on the ground")
    seen = section.index("Was the flight seen at all")
    assert ground < seen, "the ground question must be posed first"


def test_the_estimated_column_is_blanked_not_left_as_nan():
    """itables prints a missing cell as the literal string "NaN".

    90 of the 352 rows are missing -- 89 blank by design, because the
    aerodrome is measured and its real figure is in the table above, and 1
    genuinely uncomputable. They cluster at the top of the table, so the first
    thing a reader saw was five rows of "NaN".
    """
    src = chunk_source()
    assert 'fillna("—")' in src or "fillna('—')" in src, (
        "the estimated column still reaches itables carrying NaN"
    )


def test_the_reader_is_warned_that_most_estimated_values_are_zero():
    """207 of the 262 computed values are exactly 0.000.

    That is the finding -- most aerodromes outside the airport-records set
    have no ground reception at all -- but unannounced it reads as a broken
    column.
    """
    text = INDEX.read_text()
    assert "## Flights seen" in text, (
        "heading '## Flights seen' moved or was renamed; update this test"
    )
    assert "## Where these" in text, (
        "heading '## Where these' moved or was renamed; update this test"
    )
    intro = text[text.index("## Flights seen"):text.index("## Where these")]
    assert "zero" in intro.lower(), (
        "nothing warns the reader that most estimated values are 0.000"
    )


def test_the_rankings_page_has_no_collapsible_explanation_blocks():
    """The dropdowns are what the review called an overload of explanation.

    They are replaced by a tooltip per heading, with the full text on the
    Metrics page. A reintroduced `explain_block` call would put the wall of
    text back above the table.
    """
    assert "explain_block" not in INDEX.read_text()


def test_both_ranking_tables_carry_tooltip_headers():
    src = chunk_source()
    assert src.count("tip_headers(") >= 2, (
        "each ranking table's headers must carry their tooltip"
    )
    assert "table(rename(" not in src, (
        "rename() is the export path; the page must use tip_headers()"
    )


def test_the_rating_column_is_tooltipped_on_the_page_only():
    """Hovering Excellent should say what Excellent means.

    Applied in the page chunk, not in `oac.tables`, so the download keeps the
    bare word.
    """
    assert "rating_cell" in chunk_source()


def test_the_page_points_at_the_full_definitions():
    """Nothing is deleted, so the reader needs the route to the long form."""
    assert "metrics.qmd" in INDEX.read_text()


def test_both_ranking_tables_offer_a_download():
    """Remark: "could you add a download button for the ranking tables".

    Asserted on the page rather than on the files, because the files are
    gitignored build output -- what can regress here is the page forgetting to
    link them, or linking only one of the two tables.
    """
    src = chunk_source()
    for which in ("measured", "all-aerodromes"):
        assert f'downloads("{which}"' in src, f"no download button for {which}"
    assert "downloads/{stem}.xlsx" in src and "downloads/{stem}.csv" in src, (
        "both formats must be offered: CSV is universal, XLSX survives a "
        "European Excel install where a comma-separated file opens as one column"
    )
