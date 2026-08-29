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


def test_the_ranking_table_does_not_show_the_index_and_its_own_factor():
    """`signal_p50` and `coverage_index` are the same number twice.

    Measured on the 2026 sample: r = 0.998 across the 89 measured aerodromes,
    a median absolute difference of 0.0016, and the same rating band for 86 of
    them. The pair was showing a reader two columns to compare that cannot
    disagree. The dep/arr split stays on the aerodrome pages, where taxi-out
    and taxi-in really do differ -- 0.191 against 1.000 at the fleet median.
    """
    src = chunk_source()
    assert "coverage_index" in src, "the index must still be ranked on"
    assert '"signal_p50"' not in src, (
        "signal_p50 is back in a ranking table; it duplicates coverage_index"
    )


def test_the_coverage_index_formula_is_explained_where_it_is_used():
    """The formula was printed as bare identifiers with no gloss.

    A reader met `detection_rate x mean(dep_signal_p50, arr_signal_p50)` with
    nothing on the page saying what any of the three are.
    """
    text = INDEX.read_text()
    intro = text[text.index("## Ground coverage"):text.index("## Flights seen")]
    for phrase in ("seen at all", "taxi-out", "taxi-in", "median"):
        assert phrase in intro, f"the formula gloss never mentions {phrase!r}"
